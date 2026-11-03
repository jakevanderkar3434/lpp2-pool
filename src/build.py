#!/usr/bin/env python3
"""Build index.html for the LPP2 team site from league.json (+ history.json)."""
import json, re, sys, os, datetime, html
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
LEAGUE = os.path.join(HERE, "league.json")
HIST = os.path.join(HERE, "history.json")
OVR = os.path.join(HERE, "overrides.json")
OUT = os.path.join(os.path.dirname(HERE), "index.html")
CFG = os.path.join(HERE, "config.json")
SOURCE_URL = "https://shooterspool.appleague.io/league/41766977-7dfa-467e-b24f-91b2f8b5d5aa"

TEAM = "Lincoln Park Pub 2 (LPP2)"
ROSTER_NAMES_DEFAULT = ["Aidan Roberts", "Isaiah Barnett", "Jake VanDerkar", "Matt Kostura", "Seth King"]
ROSTER_IDS = []  # resolved from ROSTER_NAMES after league data loads
TZ = ZoneInfo("America/New_York")

raw = json.load(open(LEAGUE))
L = raw["league"]
fetched = raw.get("fetched_at")
now = datetime.datetime.now(TZ)

# ---------- results history (feed only shows recent items; we accumulate) ----------
hist = {"results": []}
if os.path.exists(HIST):
    hist = json.load(open(HIST))
seen = {(r["title"], r["posted"]) for r in hist["results"]}
def _parse_posted(p):
    for fmt in ("%b %d, %Y %I:%M %p", "%b %d, %Y"):
        try: return datetime.datetime.strptime(p.strip(), fmt).date()
        except ValueError: pass
    return None

def _add_result(title, posted, winner, loser, w_pts, l_pts, played=None):
    key = (title, posted)
    if key in seen: return
    if w_pts is None and played:
        pd = datetime.date.fromisoformat(played)
        for r in hist["results"]:
            if r["winner"] == winner and r["loser"] == loser and r.get("w_pts") is not None:
                rd = datetime.date.fromisoformat(r["played"]) if r.get("played") else _parse_posted(r["posted"])
                if rd and abs((rd - pd).days) <= 8:
                    seen.add(key); return
    seen.add(key)
    hist["results"].append({
        "title": title, "posted": posted, "winner": winner, "loser": loser,
        "w_pts": w_pts, "l_pts": l_pts, "played": played, "seen_at": now.isoformat(),
    })

for item in L.get("feed", []):
    if "matches" in item:
        continue
    # old format: "X beat Y, 74-51" as the title
    m = re.match(r"(.+?) beat (.+?), (\d+)-(\d+)$", item["title"])
    if m:
        _add_result(item["title"], item["date"], m.group(1), m.group(2), int(m.group(3)), int(m.group(4)))
        continue
    # new format: title "Match Results: October 26", body has one "X beat Y" per line (no scores)
    md = re.match(r"Match Results:\s*(.+)$", item["title"])
    if md and item.get("body"):
        try:
            played = datetime.datetime.strptime(md.group(1).strip() + f" {now.year}", "%B %d %Y").date()
            if played > now.date() + datetime.timedelta(days=7): played = played.replace(year=now.year - 1)
        except ValueError:
            played = None
        for line in item["body"].splitlines():
            mm = re.match(r"\s*(.+?) beat (.+?)\s*(?:,\s*(\d+)-(\d+))?\s*$", line)
            if not mm: continue
            _add_result(f"{item['title']}: {line.strip()}", item["date"], mm.group(1), mm.group(2),
                        int(mm.group(3)) if mm.group(3) else None, int(mm.group(4)) if mm.group(4) else None,
                        played.isoformat() if played else None)
json.dump(hist, open(HIST, "w"), indent=1)

config = {}
if os.path.exists(CFG):
    config = json.load(open(CFG))
AVAIL_URL = config.get("avail_url", "")

ROSTER_NAMES = config.get("roster", ROSTER_NAMES_DEFAULT)
_byname = {p["name"].strip().lower(): p["id"] for p in L["player_standings"]}
ROSTER_IDS = [_byname[n.strip().lower()] for n in ROSTER_NAMES if n.strip().lower() in _byname]
UNLISTED = [n for n in ROSTER_NAMES if n.strip().lower() not in _byname]  # on our roster but not in league stats yet

overrides = {}
if os.path.exists(OVR):
    overrides = {k: v for k, v in json.load(open(OVR)).items() if not k.startswith("_")}

def esc(s): return html.escape(str(s))
def short(name):
    m = re.search(r"\((.+?)\)$", name)
    return m.group(1) if m else name

# ---------- standings ----------
teams = sorted(L["teams"], key=lambda t: (-t["wins"], t["losses"], -t["total_points"]))
rank = {t["name"]: i + 1 for i, t in enumerate(teams)}
me = next(t for t in teams if t["name"] == TEAM)
leader = teams[0]

# ---------- schedule for our team ----------
def norm_label(lbl):
    mon, day = lbl.split()
    return f"{mon} {int(day)}"

our_sched = []
for wk, matches in L["schedule"].items():
    for m in matches:
        if TEAM in (m["home_team"], m["away_team"]):
            dt = datetime.datetime.strptime(m["date"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)
            opp = m["away_team"] if m["home_team"] == TEAM else m["home_team"]
            our_sched.append({
                "label": norm_label(m["date_formatted"]), "dt": dt,
                "opp": opp, "venue": m["court_name"],
                "home": m["home_team"] == TEAM, "past": dt.date() < now.date() or (dt.date() == now.date() and now.hour >= 23),
                "today": dt.date() == now.date(),
            })
our_sched.sort(key=lambda x: x["dt"])

# attach known results (by opponent, oldest unmatched first)
results_for_us = [r for r in hist["results"] if TEAM in (r["winner"], r["loser"])]
used = set()
for g in our_sched:
    for i, r in enumerate(results_for_us):
        if i in used: continue
        opp = r["loser"] if r["winner"] == TEAM else r["winner"]
        if opp != g["opp"]: continue
        if r.get("played"):
            if r["played"] != g["dt"].date().isoformat(): continue
        else:
            pd = _parse_posted(r["posted"])
            if pd and not (0 <= (pd - g["dt"].date()).days <= 35): continue
        won = r["winner"] == TEAM
        g["result"] = {"won": won, "us": r["w_pts"] if won else r["l_pts"], "them": r["l_pts"] if won else r["w_pts"]}
        # a 0 on our side of the feed means we forfeited (league records forfeits as X-0)
        if not won and g["result"]["us"] == 0:
            g["result"]["note"] = "Forfeit"
        used.add(i); break
# fill in our game points from roster histories where the feed gave no score
_rh = {}
for pid in ROSTER_IDS:
    for w in L.get("player_history", {}).get(str(pid), []):
        _rh.setdefault(w["label"], 0); _rh[w["label"]] += sum(g["points"] for g in w["games"])
for g in our_sched:
    if g.get("result") and g["result"].get("us") is None and _rh.get(g["label"]):
        g["result"]["us"] = _rh[g["label"]]

# manual overrides (forfeits, corrections)
for g in our_sched:
    o = overrides.get(g["label"])
    if not o: continue
    if o.get("forfeit"):
        g["result"] = {"won": o.get("result", "L") == "W", "us": o.get("us", 0), "them": o.get("them"), "note": o.get("note", "Forfeit")}
    elif "result" in o:
        g["result"] = {"won": o["result"] == "W", "us": o.get("us"), "them": o.get("them"), "note": o.get("note")}

# roster weekly points (used for inference and the team chart)
_roster_hist = {}
for pid in ROSTER_IDS:
    for w in L.get("player_history", {}).get(str(pid), []):
        _roster_hist.setdefault(w["label"], {"pts": 0, "n": 0})
        _roster_hist[w["label"]]["pts"] += sum(g["points"] for g in w["games"])
        _roster_hist[w["label"]]["n"] += len(w["games"])

# infer outcome for past matches with no posted score when the standings make it unambiguous
past_unknown = [g for g in our_sched if g["past"] and not g.get("result")]
known_w = sum(1 for g in our_sched if g.get("result") and g["result"]["won"])
known_l = sum(1 for g in our_sched if g.get("result") and not g["result"]["won"])
rem_w, rem_l = me["wins"] - known_w, me["losses"] - known_l
# standings only count matches the league has entered, so assign to the OLDEST unknown matches first
if past_unknown and (rem_w == 0 or rem_l == 0) and 0 < rem_w + rem_l <= len(past_unknown):
    for g in past_unknown[:rem_w + rem_l]:
        wk = _roster_hist.get(g["label"], {})
        g["result"] = {"won": rem_l == 0, "us": wk.get("pts") if wk.get("n") else None, "them": None, "note": None}

next_match = next((g for g in our_sched if not g["past"]), None)
last_match = next((g for g in reversed(our_sched) if g["past"]), None)

# ---------- players ----------
pstand = L["player_standings"]
prank = {p["id"]: i + 1 for i, p in enumerate(sorted(pstand, key=lambda p: -p["total_points"]))}
pbyid = {p["id"]: p for p in pstand}
ph = L.get("player_history", {})
week_labels = []
for pid in ROSTER_IDS:
    for w in ph.get(str(pid), []):
        if w["label"] not in week_labels: week_labels.append(w["label"])

players = []
for pid in ROSTER_IDS:
    p = pbyid.get(pid)
    if not p: continue
    weeks = ph.get(str(pid), [])
    games = [g for w in weeks for g in w["games"]]
    wins = sum(1 for g in games if g["result"] == "win")
    weekly = {w["label"]: {"pts": sum(g["points"] for g in w["games"]),
                           "w": sum(1 for g in w["games"] if g["result"] == "win"),
                           "n": len(w["games"])} for w in weeks}
    players.append({
        "id": pid, "name": p["name"], "pts": p["total_points"], "rank": prank[pid],
        "games": len(games), "wins": wins, "losses": len(games) - wins,
        "avg": (sum(g["points"] for g in games) / len(games)) if games else 0,
        "weekly": weekly,
    })
for n in UNLISTED:
    players.append({"id": 0, "name": n, "pts": 0, "rank": None, "games": 0, "wins": 0, "losses": 0, "avg": 0, "weekly": {}, "unlisted": True})
players.sort(key=lambda p: -p["pts"])

top_players = sorted(pstand, key=lambda p: -p["total_points"])[:10]
roster_names = {p["name"] for p in players}

# team weekly points from roster histories
# official match total (incl. handicap) when the league posted a score; otherwise roster game points
team_weekly = []
for g in our_sched:
    if not g["past"]: continue
    r = g.get("result") or {}
    wk = _roster_hist.get(g["label"], {})
    if r.get("note") == "Forfeit":
        team_weekly.append((g["label"], 0, "ff"))
    elif r.get("us") is not None and r.get("them") is not None:
        team_weekly.append((g["label"], r["us"], "official"))
    elif wk.get("n"):
        team_weekly.append((g["label"], wk["pts"], "games"))

# ---------- captains & venues (from the league's captain sheet) ----------
CAPTAINS = {
  "CT1":  {"team": "Cocktails 1",          "venue": "Cocktails",               "addr": "9208 Detroit Rd",   "captain": "Johnny V.",  "phone": "(216) 280-1722"},
  "CT2":  {"team": "Cocktails 2",          "venue": "Cocktails",               "addr": "9208 Detroit Rd",   "captain": "Brennan K.", "phone": "(469) 404-1911"},
  "LSS":  {"team": "Leather Stallion",     "venue": "Leather Stallion Saloon", "addr": "2205 St Clair Ave", "captain": "Mike I.",    "phone": "(330) 310-8501"},
  "FLEX": {"team": "Flex",                 "venue": "Leather Stallion Saloon", "addr": "2205 St Clair Ave", "captain": "Dean H.",    "phone": "(216) 645-5537"},
  "LPP1": {"team": "Lincoln Park Pub 1",   "venue": "Lincoln Park Pub",        "addr": "2609 W 14th St",    "captain": "Ryan K.",    "phone": "(216) 272-3502"},
  "LPP2": {"team": "Lincoln Park Pub 2",   "venue": "Lincoln Park Pub",        "addr": "2609 W 14th St",    "captain": "Aidan R.",   "phone": "(419) 889-0574"},
  "TSC1": {"team": "Turners 1",            "venue": "Turners",                 "addr": "1822 E 55th St",    "captain": "Nicole T.",  "phone": "(419) 908-9392"},
  "TSC2": {"team": "Turners 2",            "venue": "Turners",                 "addr": "1822 E 55th St",    "captain": "Emma M.",    "phone": "(440) 448-4250"},
  "VBE1": {"team": "Vibe 1",               "venue": "Vibe",                    "addr": "11633 Lorain Ave",  "captain": "Nick E.",    "phone": "(216) 319-5011"},
  "VBE2": {"team": "Vibe 2",               "venue": "Vibe",                    "addr": "11633 Lorain Ave",  "captain": "Ryan S.",    "phone": "(440) 752-8133"},
}
VENUE_ADDR = {v["venue"]: v["addr"] for v in CAPTAINS.values()}

# ---------- render ----------
def fmt_date(dt): return dt.strftime("%a %b ") + str(dt.day)
updated = now.strftime("%A, %B ") + str(now.day) + now.strftime(", %-I:%M %p ET")
win_pct = f"{(me['wins'] / (me['wins'] + me['losses']) * 100):.0f}%" if (me["wins"] + me["losses"]) else "—"
games_back = (leader["wins"] - me["wins"] + me["losses"] - leader["losses"]) / 2

def movement(t):
    mv = t.get("movement", 0)
    if mv > 0: return '<span class="mv up" title="Moved up">▲</span>'
    if mv < 0: return '<span class="mv down" title="Moved down">▼</span>'
    return '<span class="mv flat">•</span>'

# standings rows
st_rows = []
for i, t in enumerate(teams):
    cls = ' class="us"' if t["name"] == TEAM else ""
    st_rows.append(f"<tr{cls}><td class='rk'>{i+1}</td><td class='tm'><span class='abbr'>{esc(short(t['name']))}</span><span class='full'>{esc(re.sub(r' \(.+\)$','',t['name']))}</span></td>"
                   f"<td class='n'>{t['wins']}</td><td class='n'>{t['losses']}</td><td class='n'>{t['total_points']}</td><td class='n mvc'>{movement(t)}</td></tr>")

def score_txt(r):
    if r.get("note") == "Forfeit": return "forfeit"
    if r.get("us") is not None and r.get("them") is not None: return f"{r['us']}–{r['them']}"
    if r.get("us") is not None: return f"{r['us']} pts"
    return "no scores posted"

# schedule rows
sc_rows = []
for g in our_sched:
    cls = []
    if g["past"]: cls.append("past")
    if g is next_match: cls.append("next")
    res = ""
    if g.get("result"):
        r = g["result"]
        res = f"<span class='res {'w' if r['won'] else 'l'}'>{'W' if r['won'] else 'L'} {score_txt(r)}</span>"
    elif g["past"]:
        res = "<span class='res pending'>score pending</span>"
    elif g is next_match:
        res = "<span class='res upnext'>up next</span>"
    ha = "vs" if g["home"] else "@"
    sc_rows.append(f"<li class='{' '.join(cls)}'><span class='d'>{fmt_date(g['dt'])}</span>"
                   f"<span class='o'><span class='ha'>{ha}</span> {esc(short(g['opp']))}<span class='venue'>{esc(g['venue'])}</span></span>{res}</li>")

# player cards
maxpts = max([w["pts"] for p in players for w in p["weekly"].values()] + [1])
pcards = []
for p in players:
    bars = []
    for lbl in week_labels:
        w = p["weekly"].get(lbl)
        if not w or w["n"] == 0:
            bars.append(f"<div class='bar empty' title='{esc(lbl)}: no games'><i></i><b>{esc(lbl.split()[1])}</b></div>")
        else:
            h = max(6, round(w["pts"] / maxpts * 100))
            won = w["w"] * 2 > w["n"]
            bars.append(f"<div class='bar {'won' if won else 'lost'}' title='{esc(lbl)}: {w['pts']} pts, {w['w']}-{w['n']-w['w']}'><i style='height:{h}%'></i><b>{esc(lbl.split()[1])}</b></div>")
    first = p["name"].split()[0]
    pcards.append(f"""
    <article class="pcard" data-id="{p['id']}" tabindex="0" role="button" aria-label="Show game-by-game stats for {esc(p['name'])}">
      <header><h3>{esc(p['name'])}</h3><span class="prank">{('#' + str(p['rank']) + ' <small>of ' + str(len(pstand)) + '</small>') if p.get('rank') else '<small>new</small>'}</span></header>
      <div class="pbig"><span class="num">{p['pts']}</span><span class="lbl">points</span></div>
      <dl class="pstats">
        <div><dt>Games</dt><dd>{p['wins']}–{p['losses']}</dd></div>
        <div><dt>Avg / game</dt><dd>{p['avg']:.1f}</dd></div>
        <div><dt>Weeks played</dt><dd>{sum(1 for w in p['weekly'].values() if w['n'])}</dd></div>
      </dl>
      <div class="bars" aria-label="Points by week for {esc(first)}">{''.join(bars)}</div>
      <div class="hint">Tap for game-by-game</div>
    </article>""")

# league leaders
ld_rows = "".join(
    f"<tr{' class=us' if p['name'] in roster_names else ''}><td class='rk'>{i+1}</td><td>{esc(p['name'])}</td><td class='n'>{p['total_points']}</td></tr>"
    for i, p in enumerate(top_players))

# recent results
def _rdate(r):
    if r.get("played"): return r["played"]
    d = _parse_posted(r["posted"]); return d.isoformat() if d else ""
rr = sorted(hist["results"], key=lambda r: (_rdate(r), r["posted"]), reverse=True)[:15]
rr_rows = []
for r in rr:
    us = TEAM in (r["winner"], r["loser"])
    cls = " us" if us else ""
    sc = f"{r['w_pts']}–{r['l_pts']}" if r.get("w_pts") is not None else "def."
    when = f"<span class='rwhen'>{esc(datetime.date.fromisoformat(r['played']).strftime('%b ') + str(datetime.date.fromisoformat(r['played']).day))}</span>" if r.get("played") else ""
    rr_rows.append(f"<li class='rr{cls}'><span class='rw'>{esc(short(r['winner']))}</span><span class='score'>{sc}</span><span class='rl'>{esc(short(r['loser']))}{when}</span></li>")

next_html = "<p class='muted'>No upcoming matches on the schedule.</p>"
if next_match:
    g = next_match
    next_html = f"""
      <div class="nm-date">{'Tonight' if g['today'] else fmt_date(g['dt'])} · 7:00 PM</div>
      <div class="nm-opp"><span class="ha">{'vs' if g['home'] else '@'}</span> {esc(re.sub(r' \(.+\)$','',g['opp']))}</div>
      <div class="nm-meta">
        <span>{esc(g['venue'])}{(' · ' + esc(VENUE_ADDR[g['venue']])) if g['venue'] in VENUE_ADDR else ''}</span>
        <span>{'Home' if g['home'] else 'Away'}</span>
        <span>Captain {esc(CAPTAINS[short(g['opp'])]['captain'])} · {esc(CAPTAINS[short(g['opp'])]['phone'])}</span>
        <span>{esc(short(g['opp']))} is {rank[g['opp']]}{'st' if rank[g['opp']]==1 else 'nd' if rank[g['opp']]==2 else 'rd' if rank[g['opp']]==3 else 'th'}, {next(t for t in teams if t['name']==g['opp'])['wins']}–{next(t for t in teams if t['name']==g['opp'])['losses']}</span>
      </div>"""

last_html = ""
if last_match:
    g = last_match
    if g.get("result"):
        r = g["result"]
        last_html = f"<div class='lm'><span class='lm-l'>Last match</span> <span class='res {'w' if r['won'] else 'l'}'>{'Won' if r['won'] else 'Lost'}{' (' + score_txt(r) + ')' if score_txt(r) else ''}</span> {'vs' if g['home'] else '@'} {esc(short(g['opp']))}, {fmt_date(g['dt'])}</div>"
    else:
        last_html = f"<div class='lm'><span class='lm-l'>Last match</span> {'vs' if g['home'] else '@'} {esc(short(g['opp']))}, {fmt_date(g['dt'])} · <span class='muted'>score not posted yet</span></div>"

# ---------- team weekly (rendered in JS, with window toggle) ----------
team_weekly_json = json.dumps([{"label": l, "pts": p, "ff": k == "ff", "official": k == "official"} for l, p, k in team_weekly])

# ---------- player detail data (per-game) ----------
opp_by_week = {g["label"]: {"opp": short(g["opp"]), "home": g["home"], "venue": g["venue"]} for g in our_sched}
player_detail = []
for p in players:
    if p.get("unlisted"):
        player_detail.append({"id": 0, "name": p["name"], "pts": 0, "rank": 0, "wins": 0, "losses": 0, "avg": 0, "weeks": []})
        continue
    weeks = []
    for w in ph.get(str(p["id"]), []):
        if not w["games"]: continue
        weeks.append({"label": w["label"], "opp": opp_by_week.get(norm_label(w["label"]) if " " in w["label"] else w["label"], {}),
                      "games": [{"pts": g["points"], "opp": g["opponent_points"], "win": g["result"] == "win"} for g in w["games"]]})
    player_detail.append({"id": p["id"], "name": p["name"], "pts": p["pts"], "rank": p["rank"], "wins": p["wins"], "losses": p["losses"], "avg": round(p["avg"], 1), "weeks": weeks})
player_json = json.dumps(player_detail)

# ---------- league calendar ----------
all_matches = []
for wk, matches in L["schedule"].items():
    for m in matches:
        dt = datetime.datetime.strptime(m["date"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)
        all_matches.append({"dt": dt, "home": m["home_team"], "away": m["away_team"], "venue": m["court_name"],
                            "us": TEAM in (m["home_team"], m["away_team"])})
all_matches.sort(key=lambda m: (m["dt"], not m["us"]))
by_day = {}
for m in all_matches: by_day.setdefault(m["dt"].date(), []).append(m)

import calendar as _cal
_cal.setfirstweekday(6)  # Sunday first
first_m = min(by_day); last_m = max(by_day)
months = []
y, mo = first_m.year, first_m.month
while (y, mo) <= (last_m.year, last_m.month):
    months.append((y, mo)); mo += 1
    if mo == 13: mo = 1; y += 1
cur_month_idx = 0
focus = next_match["dt"].date() if next_match else now.date()
for i, (y, mo) in enumerate(months):
    if (y, mo) == (focus.year, focus.month): cur_month_idx = i

our_by_date = {g["dt"].date(): g for g in our_sched}

def chip(m):
    cls = "chip us" if m["us"] else "chip"
    txt = f"{short(m['away'])} @ {short(m['home'])}"
    title = f"{m['away']} at {m['home']} · {m['venue']}"
    tag = ""
    if m["us"]:
        g = our_by_date.get(m["dt"].date())
        if g and g.get("result"):
            r = g["result"]
            cls += " won" if r["won"] else " lost"
            st = score_txt(r)
            tag = f"<b>{'W' if r['won'] else 'L'}{(' ' + esc(st)) if st and st != 'forfeit' else (' FF' if st == 'forfeit' else '')}</b>"
            title += f" · {'Won' if r['won'] else 'Lost'}{(' ' + st) if st else ''}"
        elif g and g["past"]:
            cls += " pend"
            tag = "<b>?</b>"
            title += " · score pending"
    return f"<span class='{cls}' title='{esc(title)}'>{esc(txt)}{tag}</span>"

cal_months = []
for i, (y, mo) in enumerate(months):
    cells = []
    for week in _cal.monthcalendar(y, mo):
        for d in week:
            if d == 0:
                cells.append("<div class='cell blank'></div>"); continue
            date = datetime.date(y, mo, d)
            ms = by_day.get(date, [])
            cls = ["cell"]
            if ms: cls.append("has")
            if date == now.date(): cls.append("today")
            if any(m["us"] for m in ms): cls.append("ours")
            if ms and date < now.date(): cls.append("past")
            shown = [m for m in ms if m["us"]] if date < now.date() else ms
            chips = "".join(chip(m) for m in shown)
            cells.append(f"<div class='{' '.join(cls)}'><span class='dn'>{d}</span>{chips}</div>")
    # list form for narrow screens
    items = []
    for date in sorted(k for k in by_day if (k.year, k.month) == (y, mo)):
        ms = by_day[date]
        ours = any(m["us"] for m in ms)
        shown = [m for m in ms if m["us"]] if date < now.date() else ms
        if not shown: continue
        items.append(f"<li class='{'ours' if ours else ''}{' past' if date < now.date() else ''}'><span class='ld'>{date.strftime('%a')} {date.day}</span><span class='lm2'>{''.join(chip(m) for m in shown)}</span></li>")
    cal_months.append(f"""
    <div class="cal-month" data-idx="{i}"{'' if i == cur_month_idx else ' hidden'}>
      <div class="cal-grid"><div class="dow">Sun</div><div class="dow">Mon</div><div class="dow">Tue</div><div class="dow">Wed</div><div class="dow">Thu</div><div class="dow">Fri</div><div class="dow">Sat</div>{''.join(cells)}</div>
      <ul class="cal-list">{''.join(items) or "<li class='muted'>No matches this month.</li>"}</ul>
    </div>""")
month_names = json.dumps([datetime.date(y, mo, 1).strftime("%B %Y") for y, mo in months])

upcoming = [{"id": "w" + g["dt"].strftime("%Y-%m-%d"), "label": fmt_date(g["dt"]), "opp": short(g["opp"]), "home": g["home"], "venue": g["venue"]}
            for g in our_sched if not g["past"]][:3]
upcoming_json = json.dumps(upcoming)
roster_json = json.dumps([{"key": re.sub(r"[^a-z0-9]+", "-", p["name"].lower()).strip("-"), "name": p["name"]} for p in sorted(players, key=lambda p: p["name"])])

extra_css = """
/* team weekly chart */
.twhead{display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:6px;overflow:hidden}
.seg button{background:none;border:0;color:var(--chalk-2);font:600 .75rem var(--body);padding:5px 10px;cursor:pointer}
.seg button[aria-pressed="true"]{background:var(--brass);color:#1a1300}
.seg button:focus-visible{outline:2px solid var(--brass);outline-offset:-2px}
.twb i.ff{background:var(--loss);opacity:.6}
.twb.ff span{color:var(--loss)}
.twsum{font-size:.78rem;color:var(--muted);margin-top:8px}

/* player cards clickable + modal */
.pcard{cursor:pointer;transition:border-color .15s}
.pcard:hover,.pcard:focus-visible{border-color:var(--brass);outline:none}
.pcard .hint{font-size:.7rem;color:var(--brass);text-transform:uppercase;letter-spacing:.1em}
dialog.pmodal{background:var(--felt-2);color:var(--chalk);border:1px solid var(--line);border-radius:12px;padding:0;width:min(640px,calc(100vw - 32px));max-height:85vh;overflow:auto}
dialog.pmodal::backdrop{background:rgba(0,0,0,.6)}
.pm-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;padding:18px 20px 12px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--felt-2)}
.pm-head h3{font-size:1.6rem;font-weight:800;text-transform:uppercase}
.pm-head .sum{color:var(--chalk-2);font-size:.9rem;margin-top:2px}
.pm-close{background:none;border:1px solid var(--line);color:var(--chalk);border-radius:6px;width:34px;height:34px;font-size:1.1rem;cursor:pointer;flex:none}
.pm-close:focus-visible{outline:2px solid var(--brass)}
.pm-body{padding:12px 20px 20px}
.pm-week{margin-top:14px}
.pm-week h4{font:800 1rem var(--display);text-transform:uppercase;letter-spacing:.04em;margin:0 0 6px;display:flex;justify-content:space-between;gap:8px;color:var(--chalk-2)}
.pm-week h4 .wk{color:var(--chalk)}
.pm-week table{min-width:0}
.pm-week td,.pm-week th{padding:7px 10px}
.pm-week td.g{color:var(--muted)}
.pm-week .w{color:var(--win);font-weight:700} .pm-week .l{color:var(--loss);font-weight:700}
.pm-tot{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:4px}
.pm-tot div{background:var(--felt);border:1px solid var(--line);border-radius:8px;padding:8px 10px}
.pm-tot dt{font-size:.65rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)} .pm-tot dd{margin:0;font:800 1.4rem var(--display);font-variant-numeric:tabular-nums}
.pm-empty{color:var(--muted);padding:20px 0}

/* availability */
.avail{background:var(--felt-2);border:1px solid var(--line);border-radius:10px;padding:16px 18px}
.av-tabs{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px}
.av-tabs button{background:none;border:1px solid var(--line);color:var(--chalk-2);border-radius:999px;padding:6px 12px;font:600 .8rem var(--body);cursor:pointer}
.av-tabs button[aria-selected="true"]{background:var(--brass);color:#1a1300;border-color:var(--brass)}
.av-tabs button:focus-visible{outline:2px solid var(--brass);outline-offset:2px}
.av-match{display:flex;justify-content:space-between;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:10px}
.av-match .t{font:800 1.4rem var(--display);text-transform:uppercase}
.av-match .t .ha{margin-left:6px}
.av-match .sum{font-weight:600;color:var(--chalk-2);font-variant-numeric:tabular-nums}
.av-match .sum.ok{color:var(--win)} .av-match .sum.short{color:var(--loss)}
.av-rows{display:grid;gap:6px}
.av-row{display:grid;grid-template-columns:1fr auto;gap:10px;align-items:center;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--felt)}
.av-row .nm{font-weight:600}
.av-row .meta{display:block;font-size:.72rem;color:var(--muted);font-weight:400}
.av-seg{display:inline-flex;border:1px solid var(--line);border-radius:6px;overflow:hidden}
.av-seg button{background:none;border:0;border-left:1px solid var(--line);color:var(--chalk-2);font:600 .78rem var(--body);padding:7px 11px;cursor:pointer;min-width:3.2rem}
.av-seg button:first-child{border-left:0}
.av-seg button:focus-visible{outline:2px solid var(--brass);outline-offset:-2px}
.av-seg button.on.yes{background:var(--win);color:#06200f}
.av-seg button.on.maybe{background:var(--pending);color:#2a2000}
.av-seg button.on.no{background:var(--loss);color:#2a0a05}
.av-seg button:disabled{cursor:default;opacity:.7}
.av-note{font-size:.8rem;color:var(--muted);margin-top:10px}
.av-note.warn{color:var(--pending)}
.av-row.pending{opacity:.6}
@media (max-width:480px){ .av-row{grid-template-columns:1fr} .av-seg{width:100%} .av-seg button{flex:1} }

/* calendar */
.cal-head{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:10px}
.cal-nav{display:flex;align-items:center;gap:8px}
.cal-nav button{background:var(--felt-2);border:1px solid var(--line);color:var(--chalk);border-radius:6px;width:34px;height:34px;cursor:pointer;font-size:1rem}
.cal-nav button:disabled{opacity:.35;cursor:default}
.cal-nav button:focus-visible{outline:2px solid var(--brass)}
.cal-nav .mn{font:800 1.3rem var(--display);text-transform:uppercase;letter-spacing:.04em;min-width:10rem;text-align:center}
.cal-filter{display:flex;align-items:center;gap:8px;font-size:.85rem;color:var(--chalk-2);cursor:pointer;user-select:none}
.cal-filter input{accent-color:var(--brass);width:16px;height:16px}
.cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:4px}
.dow{font-size:.68rem;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);padding:4px 6px}
.cell{min-height:72px;background:var(--felt-2);border:1px solid var(--line);border-radius:6px;padding:4px 6px;min-width:0}
.cell.blank{background:none;border-color:transparent}
.cell.past{opacity:.55}
.cell.past.ours{opacity:.9}
.cell.today{border-color:var(--brass-2);box-shadow:inset 0 0 0 1px var(--brass-2)}
.cell.ours{background:linear-gradient(180deg,rgba(217,164,65,.16),var(--felt-2))}
.cell .dn{display:block;font-size:.72rem;color:var(--muted);font-variant-numeric:tabular-nums;margin-bottom:3px}
.cell.has .dn{color:var(--chalk-2);font-weight:600}
.chip{display:block;font-size:.68rem;line-height:1.25;padding:2px 4px;border-radius:3px;background:var(--rail);color:var(--chalk-2);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.chip.us{background:var(--brass);color:#1a1300;font-weight:700;display:flex;justify-content:space-between;gap:4px}
.chip.us b{flex:none;font-variant-numeric:tabular-nums}
.chip.us.won{background:var(--win);color:#06200f}
.chip.us.lost{background:var(--loss);color:#2a0a05}
.chip.us.pend{background:var(--pending);color:#2a2000}
.cell.past .chip.us{opacity:1}
.cal-wrap.only-us .chip:not(.us){display:none}
.cal-wrap.only-us .cell.has:not(.ours){opacity:.35}
.cal-list{display:none;list-style:none;margin:0;padding:0;border:1px solid var(--line);border-radius:10px;background:var(--felt-2);overflow:hidden}
.cal-list li{display:grid;grid-template-columns:4.5rem 1fr;gap:10px;padding:10px 12px;border-top:1px solid var(--line);align-items:start}
.cal-list li:first-child{border-top:0}
.cal-list li.past{opacity:.6}
.cal-list li.ours{box-shadow:inset 4px 0 0 var(--brass)}
.cal-list .ld{font-weight:600}
.cal-list .lm2{display:flex;flex-direction:column;gap:4px}
.cal-list .chip{font-size:.8rem;white-space:normal}
.cal-wrap.only-us .cal-list li:not(.ours){display:none}
.cal-legend{display:flex;gap:16px;flex-wrap:wrap;font-size:.78rem;color:var(--muted);margin-top:10px}
.cal-legend i{display:inline-block;width:12px;height:12px;border-radius:3px;vertical-align:-2px;margin-right:5px}
@media (max-width:720px){
  .cal-grid{display:none} .cal-list{display:block}
}
"""

# ---------- rules cheat sheet (from Shooters Pool League Rules & Bylaws, 2026) ----------
FAQ = [
  ("What happens if I scratch while shooting the 8-ball?",
   "If the 8-ball doesn't go in (and isn't jumped off the table), it's just a foul: your turn ends and your opponent gets ball in hand. "
   "If you pocket the 8 and scratch on the same shot, that's a loss of game. (Rules 19, 23)"),
  ("I sank the 8 by accident. Is it an automatic loss?",
   "Yes. If the 8 goes in when it isn't your legal object ball (you still have balls of your group up), it's a loss of game, accident or not. "
   "There's no spotting the 8 and playing on in this league. The only exception is the break: 8 on the break is a win (10-7), or a loss if you also scratch (10-0). (Rules 8, 17, 23e)"),
  ("What counts as ball in hand?",
   "After any foul (except where the break rules say otherwise) the incoming player may place the cue ball anywhere on the table, by hand or with the cue. "
   "Any forward stroke that touches the cue ball starts the shot. There's no minimum distance the cue ball has to travel. (Rule 15)"),
  ("I scratched on the break. Now what?",
   "It's a foul. Any balls made stay down, the table stays open, and your opponent gets ball in hand behind the head string (not anywhere). (Rule 7)"),
  ("What if the 8-ball goes in on the break?",
   "Clean break (no scratch): breaker wins, scored 10-7. Break with a scratch: breaker loses, scored 10-0. (Rules 7, 8)"),
  ("What's a legal break?",
   "Cue ball behind the head string, then either pocket a ball or drive at least 4 numbered balls to a rail. "
   "Fail that and it's a foul: your opponent can take the table as it lies, or re-rack and choose who breaks. (Rule 6)"),
  ("I made a stripe on the break. Am I stripes?",
   "No. The table is always open after the break. Groups are set only when someone legally pockets a called ball after the break. (Rule 10)"),
  ("Can I hit the 8-ball first on an open table?",
   "No, that's a foul. On an open table you can use the 8 in a combination, but the cue ball can't touch it first. (Rules 9, 16)"),
  ("Do I have to call every shot?",
   "Obvious shots don't need calling. Banks, combos and anything non-obvious do: name the ball and the pocket (not the rails or kisses). "
   "The 8-ball pocket must always be clearly called; 8 in the wrong or uncalled pocket is a loss. (Rule 2)"),
  ("What's a legal shot once groups are set?",
   "Hit one of your own balls first, then either pocket a numbered ball or send the cue ball or any numbered ball to a rail. (Rule 11)"),
  ("Can I play safe by pocketing my own ball?",
   "Yes, but you must say \"safety\" before the shot. If you don't, and you pocket your ball, you have to keep shooting. The ball stays down either way. (Rule 12)"),
  ("I accidentally pocketed an opponent's ball. Does it come back up?",
   "No. Illegally pocketed balls stay pocketed, and your turn ends if it was a foul. An illegally pocketed 8 is a loss. (Rule 17)"),
  ("A ball flew off the table.",
   "Foul and loss of turn; the ball is spotted. If it's the 8-ball, that's a loss of game. (Rule 18)"),
  ("I made my last ball and the 8 on the same stroke.",
   "Loss of game. (Rule 23b)"),
  ("Can I jump or masse around a ball?",
   "You can try, but if the blocking ball moves (by hand, cue, bridge, or follow-through) it's a cue ball foul. (Rule 5)"),
  ("Does three fouls in a row lose the game?",
   "No. The three-consecutive-fouls rule doesn't apply in this league. (Rule 15)"),
  ("How many timeouts do I get?",
   "2 coaching timeouts per game, 2 minutes each, one coach only. The coach can talk and point but can't touch balls or take practice strokes. Going over time after a warning is a foul. (Rule 20)"),
  ("Is there a shot clock?",
   "Only if a captain asks for it. Once announced, it's 1 minute per shot and running over is a foul. (Rule 21)"),
  ("My opponent is 10 minutes late for our game.",
   "They get a 15-minute grace period from when the game is called. After that it's a 10-0 forfeit (recorded FW/FL) that doesn't count toward anyone's games played or rating. They can still play later games. (Rule 22)"),
  ("Someone bumped a ball.",
   "Stop play; captains (or an agreed neutral) restore the ball as closely as possible. If it changed the shot, touched the cue ball, or is otherwise a foul under CSI rules, the foul penalty applies. Outside interference (not a player) is restored with no penalty. (Rules 24, 27)"),
  ("Nobody can make progress on the table.",
   "If both players or the captains agree it's a stalemate, re-rack and replay. The original breaker breaks again. (Rule 26)"),
  ("We disagree on a rule mid-game.",
   "Stop play. Captains try to settle it using these rules and CSI rules. If they can't, finish the game under protest and write the facts on the score sheet for the Board. "
   "Infractions must be raised before the next shot. (Rules 23, 28)"),
]

KEY_RULES = [
  ("Scoring", "Each object ball = 1 pt, the 8-ball = 3 pts, so a game is worth 10. That's where the points on this page come from. 9 games a night: 3 players, each plays 3."),
  ("Handicap", "Add the 3 shooters' skill ratings per team. The lower team gets the difference added to its final match total. It never touches individual game scores."),
  ("Skill rating", "Total points ÷ games played. You get an official rating after 3 matches (9 games). Forfeits are 10-0 but don't count as games played."),
  ("Lineup", "Visiting captain posts the first shooter, home captain the next, then alternate. Score sheet shows who breaks. Home team keeps the official sheet."),
  ("Racking", "Non-breaking team racks: 8 in the center, first ball on the foot spot, a stripe in one back corner and a solid in the other. Breaker may inspect the rack."),
  ("Roster", "3 to 6 players; only 3 shoot per night. Adds allowed through the end of the first half only, and the Statistician must approve before the new player shoots. An ineligible player forfeits their games."),
  ("Playoffs", "Played as a regular match, highest score wins. You need 16 games (4 league nights) to be eligible."),
  ("Money", "$5 per shooter per night in the team envelope ($15/night). Forfeited games still owe. Payouts at the mid-season and end-of-season parties."),
]

def faq_html():
    out = []
    for i, (q, a) in enumerate(FAQ):
        out.append(f"<details class='faq'><summary>{esc(q)}</summary><p>{esc(a)}</p></details>")
    return "".join(out)

def key_rules_html():
    return "".join(f"<div class='kr'><h3>{esc(t)}</h3><p>{esc(b)}</p></div>" for t, b in KEY_RULES)

rules_css = """
/* rules */
.loss{background:var(--felt-2);border:1px solid var(--line);border-left:4px solid var(--loss);border-radius:10px;padding:14px 18px;margin-bottom:16px}
.loss h3{font:800 1.1rem var(--display);text-transform:uppercase;letter-spacing:.05em;color:var(--loss);margin-bottom:6px}
.loss ul{margin:0;padding-left:1.1rem;columns:2;column-gap:24px;font-size:.92rem}
.loss li{break-inside:avoid;margin-bottom:4px}
.krgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin-bottom:20px}
.kr{background:var(--felt-2);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.kr h3{font:800 1.05rem var(--display);text-transform:uppercase;letter-spacing:.05em;color:var(--brass);margin-bottom:4px}
.kr p{margin:0;font-size:.9rem;color:var(--chalk-2)}
.faqwrap{border:1px solid var(--line);border-radius:10px;background:var(--felt-2);overflow:hidden}
.faq{border-top:1px solid var(--line)}
.faq:first-child{border-top:0}
.faq summary{cursor:pointer;padding:12px 16px;font-weight:600;list-style:none;display:flex;justify-content:space-between;gap:12px;align-items:center}
.faq summary::-webkit-details-marker{display:none}
.faq summary::after{content:"+";color:var(--brass);font:800 1.2rem var(--display);flex:none}
.faq[open] summary::after{content:"–"}
.faq summary:focus-visible{outline:2px solid var(--brass);outline-offset:-2px}
.faq p{margin:0;padding:0 16px 14px;color:var(--chalk-2);font-size:.92rem;max-width:70ch}
.rules-foot{font-size:.8rem;color:var(--muted);margin-top:10px}
.rules-two{margin-bottom:20px}
.rh{font:800 1.15rem var(--display);text-transform:uppercase;letter-spacing:.05em;color:var(--chalk-2);margin-bottom:8px}
table.eight{min-width:0}
table.eight td{font-size:.9rem;vertical-align:top}
table.eight .ok{color:var(--win);font-weight:700} table.eight .bad{color:var(--loss);font-weight:700}
.safety{background:var(--felt-2);border:1px solid var(--line);border-radius:10px;padding:12px 16px}
.safety ol{margin:0;padding-left:1.2rem;font-size:.92rem;color:var(--chalk-2);display:grid;gap:8px}
.safety li b{color:var(--chalk)}
@media (max-width:600px){ .loss ul{columns:1} }
"""
extra_css += rules_css

rules_html = f"""
<section id="rules">
  <h2>Rules cheat sheet <small>Shooters Pool League Rules &amp; Bylaws, 2026 revision · CSI/BCA rules apply where these are silent</small></h2>
  <div class="loss">
    <h3>Instant loss of game</h3>
    <ul>
      <li>Foul (incl. scratch) while pocketing the 8</li>
      <li>8 in the wrong or uncalled pocket</li>
      <li>8 and your last ball on the same stroke</li>
      <li>8 pocketed when it isn't your legal object ball</li>
      <li>8 jumped off the table</li>
      <li>8 on the break <em>with</em> a scratch (10-0)</li>
    </ul>
  </div>
  <div class="krgrid">{key_rules_html()}</div>
  <div class="two rules-two">
    <div>
      <h3 class="rh">Shooting the 8: what ends the game and what doesn't</h3>
      <div class="tblwrap"><table class="eight">
        <thead><tr><th>You're on the 8 and&hellip;</th><th>Result</th></tr></thead>
        <tbody>
          <tr><td>You scratch, 8 stays on the table</td><td><span class="ok">Foul</span> · ball in hand, game continues</td></tr>
          <tr><td>You miss the 8 and nothing hits a rail</td><td><span class="ok">Foul</span> · ball in hand, game continues</td></tr>
          <tr><td>Cue ball hits an opponent's ball first, 8 doesn't drop</td><td><span class="ok">Foul</span> · ball in hand, game continues</td></tr>
          <tr><td>You scratch <em>and</em> the 8 drops</td><td><span class="bad">Loss</span></td></tr>
          <tr><td>8 goes in the wrong or uncalled pocket</td><td><span class="bad">Loss</span></td></tr>
          <tr><td>8 and your last group ball drop on the same stroke</td><td><span class="bad">Loss</span></td></tr>
          <tr><td>8 jumps off the table</td><td><span class="bad">Loss</span></td></tr>
          <tr><td>8 drops while you still have group balls up</td><td><span class="bad">Loss</span> · accident or not</td></tr>
        </tbody>
      </table></div>
      <p class="rules-foot">The 8 has to actually be pocketed or jumped for the game to end (Rule 19). The real risk of a foul on the 8 is handing your opponent ball in hand, not losing on the spot.</p>
    </div>
    <div>
      <h3 class="rh">Safeties (Rule 12)</h3>
      <div class="safety">
        <ol>
          <li><b>Say it first.</b> Tell your opponent "safety" before the shot. A safety you didn't announce isn't a safety.</li>
          <li><b>It still has to be a legal shot.</b> Hit your own ball first, then pocket a ball or get the cue ball or any numbered ball to a rail. Otherwise it's a foul and ball in hand.</li>
          <li><b>Your turn ends after the shot</b>, even if you pocket your ball.</li>
          <li><b>Anything you pocket stays down.</b> A ball pocketed on a declared safety counts as illegally pocketed, so it doesn't earn you another shot, but it doesn't come back up either.</li>
          <li><b>Forgot to call it?</b> If you pocket one of your balls, you must keep shooting. You can't bail out of your turn after the fact.</li>
          <li><b>You don't need to declare a safety</b> on a shot that isn't going to pocket anything. Just play the leave; if you make a legal hit, your turn ends normally.</li>
        </ol>
        <p class="rules-foot">Why it matters: a called safety lets you dump an easy ball to leave your opponent nothing, without being forced to keep shooting from a bad position.</p>
      </div>
    </div>
  </div>
  <div class="faqwrap">{faq_html()}</div>
  <p class="rules-foot">Summarized for quick reference. The official document and League Board contacts (Statistician, Treasurer, Event Director, At-Large) are in the team folder and the rules PDF; the PDF controls if anything here disagrees.</p>
</section>
"""


def cap_rows():
    order = [short(t["name"]) for t in teams]  # standings order
    out = []
    for ab in order:
        c = CAPTAINS.get(ab)
        if not c: continue
        us = " class='us'" if ab == "LPP2" else ""
        out.append(f"<tr{us}><td><b>{esc(c['team'])}</b> <span class='muted'>{esc(ab)}</span></td><td>{esc(c['captain'])}</td>"
                   f"<td class='ph'><span class='num'>{esc(c['phone'])}</span><button type='button' class='copy' data-copy='{esc(c['phone'])}' aria-label='Copy {esc(c['captain'])} phone number'>Copy</button></td>"
                   f"<td>{esc(c['venue'])}<span class='venue'>{esc(c['addr'])}</span></td></tr>")
    return "".join(out)

captains_html = f"""
<section id="captains">
  <h2>Captains &amp; venues <small>in standings order · tap Copy to grab a number</small></h2>
  <div class="tblwrap"><table class="caps">
    <thead><tr><th>Team</th><th>Captain</th><th>Phone</th><th>Venue</th></tr></thead>
    <tbody>{cap_rows()}</tbody>
  </table></div>
  <p class="rules-foot">From the league captain sheet. Numbers are for league business only.</p>
</section>
"""
extra_css += """
/* captains */
table.caps{min-width:560px}
table.caps td{vertical-align:top;font-size:.92rem}
table.caps .venue{display:block;font-size:.78rem;color:var(--muted)}
table.caps .ph{white-space:nowrap}
table.caps .num{font-variant-numeric:tabular-nums;user-select:all}
.copy{margin-left:8px;background:none;border:1px solid var(--line);color:var(--chalk-2);border-radius:5px;padding:2px 8px;font:600 .72rem var(--body);cursor:pointer;vertical-align:1px}
.copy:hover{border-color:var(--brass);color:var(--brass)}
.copy:focus-visible{outline:2px solid var(--brass)}
.copy.done{background:var(--brass);color:#1a1300;border-color:var(--brass)}
"""

script_js = r"""
<script>
(function(){
  var TW = __TW__, PLAYERS = __PLAYERS__, MONTHS = __MONTHS__, CUR = __CUR__, UPCOMING = __UPCOMING__, ROSTER = __ROSTER__, AVAIL_URL = __AVAIL_URL__;

  /* ---- schedule collapse ---- */
  var ul=document.getElementById('sched'), btn=document.getElementById('showall');
  var items=[].slice.call(ul.children);
  var nextIdx=items.findIndex(function(li){return li.classList.contains('next')});
  if(nextIdx<0) nextIdx=items.length-1;
  items.forEach(function(li,i){ if(i<nextIdx-3||i>nextIdx+3) li.classList.add('far'); });
  var collapsed=true;
  btn.addEventListener('click',function(){
    collapsed=!collapsed; ul.classList.toggle('collapsed',collapsed);
    btn.textContent=collapsed?'Show full season':'Show fewer';
  });
  if(items.filter(function(li){return li.classList.contains('far')}).length===0) btn.hidden=true;

  /* ---- team points by week ---- */
  var twEl=document.getElementById('tw'), twSum=document.getElementById('twsum');
  var win=4;
  function renderTW(){
    var rows=win===0?TW:TW.slice(-win);
    if(!rows.length){ twEl.innerHTML="<p class='muted'>No game scores posted yet.</p>"; return; }
    var mx=Math.max.apply(null,rows.map(function(r){return r.pts})) || 1;
    twEl.innerHTML=rows.map(function(r){
      var h=Math.max(4,Math.round(r.pts/mx*100));
      return "<div class='twb"+(r.ff?" ff":"")+"' title='"+r.label+": "+(r.ff?"forfeit":r.pts+(r.official?" match total (incl. handicap)":" game pts, official total not posted yet"))+"'><i class='"+(r.ff?"ff":"")+"' style='height:"+h+"%'></i><b>"+r.label+"</b><span>"+(r.ff?"FF":r.pts+(r.official?"":"*"))+"</span></div>";
    }).join("");
    var played=rows.filter(function(r){return !r.ff});
    var avg=played.length?Math.round(played.reduce(function(a,r){return a+r.pts},0)/played.length):0;
    var unofficial=played.some(function(r){return !r.official});
    twSum.textContent=(win===0?"Season":"Last "+rows.length+(rows.length===1?" week":" weeks"))+" · avg "+avg+" per match played · official match totals incl. handicap"+(unofficial?" (* = game points only, score not posted yet)":"");
    document.querySelectorAll('#twseg button').forEach(function(b){b.setAttribute('aria-pressed', String(+b.dataset.win===win))});
  }
  document.querySelectorAll('#twseg button').forEach(function(b){ b.addEventListener('click',function(){ win=+b.dataset.win; renderTW(); }); });
  renderTW();

  /* ---- player detail modal ---- */
  var dlg=document.getElementById('pmodal'), pmBody=document.getElementById('pm-body'), pmName=document.getElementById('pm-name'), pmSum=document.getElementById('pm-sum');
  function openPlayer(id){
    var p=PLAYERS.find(function(x){return String(x.id)===String(id)}); if(!p) return;
    pmName.textContent=p.name;
    pmSum.textContent=p.rank?("#"+p.rank+" in the league · "+p.pts+" pts · "+p.wins+"–"+p.losses+" in games · "+p.avg.toFixed(1)+" avg"):"New to the roster · no league games recorded yet";
    if(!p.weeks.length){ pmBody.innerHTML="<p class='pm-empty'>No games recorded yet for "+p.name.split(' ')[0]+".</p>"; }
    else{
      var best=Math.max.apply(null,p.weeks.map(function(w){return w.games.reduce(function(a,g){return a+g.pts},0)}));
      var tens=p.weeks.reduce(function(a,w){return a+w.games.filter(function(g){return g.pts===10}).length},0);
      var html="<dl class='pm-tot'><div><dt>Best week</dt><dd>"+best+"</dd></div><div><dt>10-point games</dt><dd>"+tens+"</dd></div><div><dt>Weeks played</dt><dd>"+p.weeks.length+"</dd></div></dl>";
      p.weeks.slice().reverse().forEach(function(w){
        var tot=w.games.reduce(function(a,g){return a+g.pts},0), ww=w.games.filter(function(g){return g.win}).length;
        var opp=w.opp&&w.opp.opp?(w.opp.home?"vs ":"@ ")+w.opp.opp+" · "+w.opp.venue:"";
        html+="<div class='pm-week'><h4><span class='wk'>"+w.label+"</span><span>"+opp+"</span></h4><div class='tblwrap'><table><thead><tr><th>Game</th><th class='n'>"+p.name.split(' ')[0]+"</th><th class='n'>Opp</th><th class='n'>Result</th></tr></thead><tbody>";
        w.games.forEach(function(g,i){ html+="<tr><td class='g'>Game "+(i+1)+"</td><td class='n'>"+g.pts+"</td><td class='n'>"+g.opp+"</td><td class='n'><span class='"+(g.win?"w":"l")+"'>"+(g.win?"W":"L")+"</span></td></tr>"; });
        html+="<tr class='us'><td>Week total</td><td class='n'>"+tot+"</td><td class='n'>"+w.games.reduce(function(a,g){return a+g.opp},0)+"</td><td class='n'>"+ww+"–"+(w.games.length-ww)+"</td></tr></tbody></table></div></div>";
      });
      pmBody.innerHTML=html;
    }
    if(typeof dlg.showModal==='function') dlg.showModal(); else dlg.setAttribute('open','');
  }
  document.querySelectorAll('.pcard').forEach(function(c){
    c.addEventListener('click',function(){openPlayer(c.dataset.id)});
    c.addEventListener('keydown',function(e){ if(e.key==='Enter'||e.key===' '){e.preventDefault();openPlayer(c.dataset.id);} });
  });
  document.getElementById('pm-close').addEventListener('click',function(){dlg.close()});
  dlg.addEventListener('click',function(e){ if(e.target===dlg) dlg.close(); });

  /* ---- availability (Google Apps Script + Sheet, no sign-in) ---- */
  (function(){
    var tabs=document.getElementById('av-tabs'), matchEl=document.getElementById('av-match'), rows=document.getElementById('av-rows'), note=document.getElementById('av-note');
    var state={}, cur=0, busy=false, offline=false, loaded=false;
    var STATUSES=[['yes','In'],['maybe','Maybe'],['no','Out']];
    function fmtWhen(ts){ try{ var d=new Date(ts); return d.toLocaleDateString(undefined,{month:'short',day:'numeric'})+' '+d.toLocaleTimeString(undefined,{hour:'numeric',minute:'2-digit'}); }catch(e){ return ''; } }
    function render(){
      if(!UPCOMING.length){ matchEl.innerHTML=''; rows.innerHTML=''; note.textContent='No upcoming matches on the schedule.'; tabs.innerHTML=''; return; }
      tabs.innerHTML=UPCOMING.map(function(m,i){ return "<button type='button' role='tab' aria-selected='"+(i===cur)+"' data-i='"+i+"'>"+m.label+"</button>"; }).join('');
      var m=UPCOMING[cur], wk=state[m.id]||{};
      var yes=ROSTER.filter(function(p){return (wk[p.key]||{}).status==='yes'}).length;
      var no=ROSTER.filter(function(p){return (wk[p.key]||{}).status==='no'}).length;
      var cls=yes>=4?'ok':(ROSTER.length-no<4?'short':'');
      matchEl.innerHTML="<div class='t'>"+m.label+" <span class='ha'>"+(m.home?'vs':'@')+"</span> "+m.opp+" <small class='muted' style='font:500 .85rem var(--body);text-transform:none'>· "+m.venue+"</small></div><div class='sum "+cls+"'>"+yes+" in · "+no+" out · "+(ROSTER.length-yes-no)+" unanswered</div>";
      var locked = !AVAIL_URL || busy;
      rows.innerHTML=ROSTER.map(function(p){
        var st=wk[p.key]||{}, meta=st.status?("<span class='meta'>"+(st.at?fmtWhen(st.at):'')+"</span>"):"<span class='meta'>not answered</span>";
        return "<div class='av-row"+(st.status?'':' pending')+"'><span class='nm'>"+p.name+meta+"</span><span class='av-seg' role='group' aria-label='"+p.name+" availability'>"+
          STATUSES.map(function(sv){ return "<button type='button' class='"+sv[0]+(st.status===sv[0]?' on':'')+"' data-p='"+p.key+"' data-s='"+sv[0]+"'"+(locked?' disabled':'')+">"+sv[1]+"</button>"; }).join('')+"</span></div>";
      }).join('');
      if(!AVAIL_URL){ note.className='av-note warn'; note.textContent='Availability sign-up isn\'t connected yet.'; }
      else if(offline){ note.className='av-note warn'; note.textContent='Couldn\'t reach the sign-up sheet. Check your connection and try again.'; }
      else if(!loaded){ note.className='av-note'; note.textContent='Loading availability…'; }
      else { note.className='av-note'; note.textContent='Tap your name\'s button. Anyone on the team can update anyone, so you can mark a teammate who texted you. Tap again to clear.'; }
    }
    function load(){
      if(!AVAIL_URL) return;
      fetch(AVAIL_URL+'?t='+Date.now(),{cache:'no-store'}).then(function(r){return r.json()}).then(function(data){
        var next={};
        (data.rows||[]).forEach(function(v){ if(!v.week||!v.player) return; next[v.week]=next[v.week]||{}; next[v.week][v.player]=v; });
        state=next; loaded=true; offline=false; render();
      }).catch(function(){ offline=true; render(); });
    }
    tabs.addEventListener('click',function(e){ var b=e.target.closest('button'); if(!b) return; cur=+b.dataset.i; render(); });
    rows.addEventListener('click',function(e){
      var b=e.target.closest('button'); if(!b||b.disabled||!AVAIL_URL) return;
      var m=UPCOMING[cur], prev=(state[m.id]||{})[b.dataset.p]||{};
      var body={week:m.id, player:b.dataset.p, status:(prev.status===b.dataset.s)?'':b.dataset.s, at:new Date().toISOString()};
      state[m.id]=state[m.id]||{}; state[m.id][b.dataset.p]=body; busy=true; render();
      fetch(AVAIL_URL,{method:'POST',headers:{'Content-Type':'text/plain;charset=utf-8'},body:JSON.stringify(body)})
        .then(function(r){ return r.text(); }).then(function(){ busy=false; load(); })
        .catch(function(){ busy=false; offline=true; render(); });
    });
    render(); load();
    setInterval(function(){ if(document.visibilityState==='visible') load(); }, 30000);
    document.addEventListener('visibilitychange',function(){ if(document.visibilityState==='visible') load(); });
  })();

  /* ---- copy buttons ---- */
  document.querySelectorAll('.copy').forEach(function(b){
    b.addEventListener('click',function(){
      var t=b.dataset.copy, done=function(){ b.textContent='Copied'; b.classList.add('done'); setTimeout(function(){b.textContent='Copy';b.classList.remove('done')},1500); };
      if(navigator.clipboard&&navigator.clipboard.writeText){ navigator.clipboard.writeText(t).then(done).catch(function(){ selectNum(); }); } else selectNum();
      function selectNum(){ var n=b.previousElementSibling, r=document.createRange(); r.selectNodeContents(n); var sel=window.getSelection(); sel.removeAllRanges(); sel.addRange(r); }
    });
  });

  /* ---- calendar ---- */
  var cur=CUR, mEls=document.querySelectorAll('.cal-month'), mn=document.getElementById('cal-mn');
  var prev=document.getElementById('cal-prev'), next=document.getElementById('cal-next');
  function showMonth(){
    mEls.forEach(function(el){ el.hidden = +el.dataset.idx!==cur; });
    mn.textContent=MONTHS[cur]; prev.disabled=cur===0; next.disabled=cur===MONTHS.length-1;
  }
  prev.addEventListener('click',function(){ if(cur>0){cur--;showMonth();} });
  next.addEventListener('click',function(){ if(cur<MONTHS.length-1){cur++;showMonth();} });
  var onlyUs=document.getElementById('cal-only'), calWrap=document.getElementById('cal');
  onlyUs.addEventListener('change',function(){ calWrap.classList.toggle('only-us', onlyUs.checked); });
  showMonth();
})();
</script>
""".replace("__TW__", team_weekly_json).replace("__PLAYERS__", player_json).replace("__MONTHS__", month_names).replace("__CUR__", str(cur_month_idx)).replace("__UPCOMING__", upcoming_json).replace("__ROSTER__", roster_json).replace("__AVAIL_URL__", json.dumps(AVAIL_URL))

page = f"""<title>LPP2 Pool League</title>
<meta name="description" content="Lincoln Park Pub 2 team page for Shooters Pool League '26">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;800&family=Barlow:wght@400;500;600&display=swap">
<style>
/* Layout: one column, 960px max, dark pool-hall felt with chalk-white type and brass accents. Standings and schedule as plain tables; players as a card row. */
:root{{
  --felt:#0f2a1f; --felt-2:#143627; --rail:#1c4332; --line:rgba(255,255,255,.10);
  --chalk:#f1ede4; --chalk-2:#b9c4bd; --muted:#7f948a;
  --brass:#d9a441; --brass-2:#f0c35e;
  --win:#5ecb86; --loss:#e26d5c; --pending:#c9b16a;
  --display:"Barlow Condensed", "Arial Narrow", Impact, sans-serif;
  --body:"Barlow", "Helvetica Neue", Arial, sans-serif;
  color-scheme:dark;
}}
@media (prefers-color-scheme: light){{ :root:not([data-theme="dark"]){{
  --felt:#e9ede8; --felt-2:#ffffff; --rail:#dfe6e1; --line:rgba(15,42,31,.12);
  --chalk:#132a20; --chalk-2:#355046; --muted:#6a7f74;
  --brass:#a86f12; --brass-2:#8a5a0c; --win:#1f8a4c; --loss:#b8402f; --pending:#8a6d12;
  color-scheme:light;
}} }}
:root[data-theme="light"]{{
  --felt:#e9ede8; --felt-2:#ffffff; --rail:#dfe6e1; --line:rgba(15,42,31,.12);
  --chalk:#132a20; --chalk-2:#355046; --muted:#6a7f74;
  --brass:#a86f12; --brass-2:#8a5a0c; --win:#1f8a4c; --loss:#b8402f; --pending:#8a6d12;
  color-scheme:light;
}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--felt);color:var(--chalk);font-family:var(--body);font-size:16px;line-height:1.45;
  background-image:radial-gradient(ellipse at 50% -10%, rgba(255,255,255,.07), transparent 60%);}}
.wrap{{max-width:960px;margin:0 auto;padding-block:28px 56px;padding-inline:20px}}
h1,h2,h3{{font-family:var(--display);text-wrap:balance;margin:0;letter-spacing:.01em}}
h2{{font-size:1.5rem;font-weight:800;text-transform:uppercase;letter-spacing:.06em;color:var(--chalk-2);margin-bottom:12px;display:flex;align-items:baseline;gap:12px}}
h2 small{{font:500 .8rem var(--body);letter-spacing:0;text-transform:none;color:var(--muted)}}
section{{margin-top:40px}}
.muted{{color:var(--muted)}}
.n{{text-align:right;font-variant-numeric:tabular-nums}}

/* masthead */
.mast{{display:flex;flex-wrap:wrap;align-items:flex-end;justify-content:space-between;gap:16px;border-bottom:2px solid var(--brass);padding-bottom:16px}}
.mast .team{{display:flex;align-items:center;gap:18px}}
.ball{{width:64px;height:64px;border-radius:50%;background:radial-gradient(circle at 35% 30%, #fff8e0, var(--brass) 55%, #7a5210);display:grid;place-items:center;flex:none;box-shadow:inset -6px -8px 14px rgba(0,0,0,.35), 0 6px 14px rgba(0,0,0,.35)}}
.ball span{{background:#fff;color:#111;border-radius:50%;width:32px;height:32px;display:grid;place-items:center;font:800 18px var(--display)}}
.mast h1{{font-size:clamp(2.4rem,7vw,3.6rem);font-weight:800;line-height:.95;text-transform:uppercase}}
.mast .sub{{color:var(--chalk-2);font-weight:500;margin-top:4px}}
.mast .upd{{color:var(--muted);font-size:.85rem;text-align:right}}
.mast .upd b{{display:block;color:var(--chalk-2);font-weight:600}}

/* tiles */
.tiles{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:24px}}
.tile{{background:var(--felt-2);border:1px solid var(--line);border-radius:10px;padding:14px 16px}}
.tile .lbl{{font-size:.75rem;text-transform:uppercase;letter-spacing:.1em;color:var(--muted)}}
.tile .val{{font:800 2.4rem/1 var(--display);margin-top:6px;font-variant-numeric:tabular-nums}}
.tile .val small{{font:600 1rem var(--display);color:var(--muted);margin-left:4px}}
.tile .sub{{font-size:.8rem;color:var(--chalk-2);margin-top:4px}}

/* next match */
.hero{{display:grid;grid-template-columns:1.2fr .8fr;gap:16px;margin-top:16px}}
.next{{background:linear-gradient(135deg,var(--rail),var(--felt-2));border:1px solid var(--line);border-left:4px solid var(--brass);border-radius:10px;padding:18px 20px}}
.next .k{{font-size:.75rem;text-transform:uppercase;letter-spacing:.12em;color:var(--brass)}}
.nm-date{{font:600 1.1rem var(--body);color:var(--chalk-2);margin-top:6px}}
.nm-opp{{font:800 clamp(1.8rem,5vw,2.6rem)/1.05 var(--display);text-transform:uppercase;margin-top:4px}}
.ha{{color:var(--brass);font-weight:800}}
.nm-meta{{display:flex;flex-wrap:wrap;gap:8px 18px;margin-top:10px;color:var(--chalk-2);font-size:.9rem}}
.nm-meta span::before{{content:"";display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--brass);margin-right:8px;vertical-align:middle}}
.lm{{margin-top:14px;padding-top:12px;border-top:1px dashed var(--line);font-size:.9rem;color:var(--chalk-2)}}
.lm-l{{text-transform:uppercase;letter-spacing:.1em;font-size:.72rem;color:var(--muted);margin-right:6px}}
.twcard{{background:var(--felt-2);border:1px solid var(--line);border-radius:10px;padding:16px 18px;display:flex;flex-direction:column}}
.twcard .k{{font-size:.75rem;text-transform:uppercase;letter-spacing:.12em;color:var(--muted)}}
.tw{{display:flex;gap:10px;align-items:flex-end;height:120px;margin-top:auto;padding-top:12px}}
.twb{{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;min-width:0}}
.twb i{{display:block;width:100%;max-width:56px;background:var(--brass);border-radius:4px 4px 0 0;opacity:.9}}
.twb b{{font:600 .72rem var(--body);color:var(--muted);margin-top:6px;white-space:nowrap}}
.twb span{{font:800 .95rem var(--display);color:var(--chalk);order:-1;margin-bottom:4px;font-variant-numeric:tabular-nums}}

/* tables */
.tblwrap{{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--felt-2)}}
table{{width:100%;border-collapse:collapse;min-width:420px}}
th,td{{padding:10px 14px;text-align:left;border-top:1px solid var(--line)}}
th{{font-size:.72rem;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);border-top:0;font-weight:600}}
th.n{{text-align:right}}
tr.us td{{background:rgba(217,164,65,.12);font-weight:600}}
tr.us td.tm::after{{content:"us";font:700 .6rem var(--body);letter-spacing:.1em;text-transform:uppercase;background:var(--brass);color:#1a1300;border-radius:3px;padding:2px 5px;margin-left:8px;vertical-align:middle}}
td.rk{{color:var(--muted);width:2.5rem;font-variant-numeric:tabular-nums}}
td.tm .abbr{{display:none;font-weight:700}}
td.tm .full{{display:inline}}
.mv{{font-size:.75rem}} .mv.up{{color:var(--win)}} .mv.down{{color:var(--loss)}} .mv.flat{{color:var(--muted)}}
.mvc{{width:2.5rem}}

/* two-up */
.two{{display:grid;grid-template-columns:1.1fr .9fr;gap:24px}}

/* schedule */
.sched{{list-style:none;margin:0;padding:0;border:1px solid var(--line);border-radius:10px;background:var(--felt-2);overflow:hidden}}
.sched li{{display:grid;grid-template-columns:5.5rem 1fr auto;gap:12px;align-items:center;padding:10px 14px;border-top:1px solid var(--line)}}
.sched li:first-child{{border-top:0}}
.sched li.past{{color:var(--chalk-2)}}
.sched li.past .d{{color:var(--muted)}}
.sched li.next{{background:rgba(217,164,65,.14);box-shadow:inset 4px 0 0 var(--brass)}}
.sched .d{{font-weight:600;font-variant-numeric:tabular-nums;white-space:nowrap}}
.sched .o{{min-width:0;font-weight:500}}
.sched .venue{{display:block;font-size:.78rem;color:var(--muted)}}
.res{{font:800 .95rem var(--display);letter-spacing:.03em;white-space:nowrap;font-variant-numeric:tabular-nums}}
.res.w{{color:var(--win)}} .res.l{{color:var(--loss)}} .res.pending{{color:var(--pending);font:500 .78rem var(--body)}} .res.upnext{{color:var(--brass);font-size:.85rem;text-transform:uppercase}}
.showall{{margin-top:10px;background:none;border:1px solid var(--line);color:var(--chalk-2);border-radius:6px;padding:8px 14px;font:600 .85rem var(--body);cursor:pointer}}
.showall:focus-visible{{outline:2px solid var(--brass);outline-offset:2px}}
.sched.collapsed li.far{{display:none}}

/* players */
.pgrid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}}
.pcard{{background:var(--felt-2);border:1px solid var(--line);border-radius:10px;padding:14px 16px;display:flex;flex-direction:column;gap:10px;min-width:0}}
.pcard header{{display:flex;justify-content:space-between;align-items:baseline;gap:8px}}
.pcard h3{{font-size:1.25rem;font-weight:800;text-transform:uppercase}}
.prank{{font:600 .8rem var(--body);color:var(--brass);white-space:nowrap}} .prank small{{color:var(--muted);font-weight:500}}
.pbig .num{{font:800 2.6rem/1 var(--display);font-variant-numeric:tabular-nums}} .pbig .lbl{{font-size:.75rem;color:var(--muted);text-transform:uppercase;letter-spacing:.1em;margin-left:6px}}
.pstats{{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin:0}}
.pstats div{{min-width:0}} .pstats dt{{font-size:.65rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}} .pstats dd{{margin:0;font-weight:600;font-variant-numeric:tabular-nums}}
.bars{{display:flex;gap:6px;align-items:flex-end;height:64px;border-top:1px solid var(--line);padding-top:8px;margin-top:auto}}
.bar{{flex:1;height:100%;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;min-width:0}}
.bar i{{display:block;width:100%;border-radius:3px 3px 0 0;background:var(--chalk-2)}}
.bar.won i{{background:var(--win)}} .bar.lost i{{background:var(--loss)}} .bar.empty i{{height:2px;background:var(--line)}}
.bar b{{font:500 .62rem var(--body);color:var(--muted);margin-top:4px}}
.legend{{font-size:.78rem;color:var(--muted);margin-top:10px;display:flex;gap:14px;flex-wrap:wrap}}
.legend i{{display:inline-block;width:10px;height:10px;border-radius:2px;vertical-align:-1px;margin-right:5px}}

/* results */
.rlist{{list-style:none;margin:0;padding:0;display:grid;gap:8px}}
.rr{{display:grid;grid-template-columns:1fr auto 1fr;gap:12px;align-items:center;background:var(--felt-2);border:1px solid var(--line);border-radius:8px;padding:10px 14px;font-weight:600}}
.rr .rw{{text-align:right}} .rr .rl{{color:var(--muted);font-weight:500}}
.rr .score{{font:800 1.2rem var(--display);font-variant-numeric:tabular-nums;color:var(--brass)}}
.rr.us{{border-color:var(--brass)}}

footer{{margin-top:48px;border-top:1px solid var(--line);padding-top:16px;color:var(--muted);font-size:.82rem;display:flex;flex-wrap:wrap;gap:8px 24px;justify-content:space-between}}
footer a{{color:var(--chalk-2)}}

@media (max-width:720px){{
  .tiles{{grid-template-columns:repeat(2,1fr)}}
  .hero,.two{{grid-template-columns:1fr}}
  .mast .upd{{text-align:left}}
  td.tm .abbr{{display:inline}} td.tm .full{{display:none}}
  table{{min-width:0}}
  th,td{{padding:9px 10px}}
}}
@media (prefers-reduced-motion:no-preference){{
  .bar i,.twb i{{transition:height .4s ease}}
}}
{extra_css}
</style>

<div class="wrap">
<header class="mast">
  <div class="team">
    <div class="ball" aria-hidden="true"><span>2</span></div>
    <div>
      <h1>LPP2</h1>
      <div class="sub">Lincoln Park Pub 2 · Shooters Pool League '26</div>
    </div>
  </div>
  <div class="upd"><b>Updated {esc(updated)}</b>Refreshes Tue 6 PM &amp; Wed 9 AM</div>
</header>

<div class="tiles">
  <div class="tile"><div class="lbl">Record</div><div class="val">{me['wins']}–{me['losses']}</div><div class="sub">Win rate {win_pct}</div></div>
  <div class="tile"><div class="lbl">Standing</div><div class="val">{rank[TEAM]}<small>of {len(teams)}</small></div><div class="sub">{games_back:g} games back of {esc(short(leader['name']))}</div></div>
  <div class="tile"><div class="lbl">Team points</div><div class="val">{me['total_points']}</div><div class="sub">Leader has {leader['total_points']}</div></div>
  <div class="tile"><div class="lbl">Last week</div><div class="val">{me.get('wins_lastweek',0)}–{me.get('losses_lastweek',0)}</div><div class="sub">Matches recorded</div></div>
</div>

<div class="hero">
  <div class="next"><div class="k">Next match</div>{next_html}{last_html}</div>
  <div class="twcard">
    <div class="twhead"><div class="k">Match total by week</div>
      <div class="seg" id="twseg" role="group" aria-label="Weeks shown"><button type="button" data-win="4">4 wk</button><button type="button" data-win="8">8 wk</button><button type="button" data-win="0">Season</button></div>
    </div>
    <div class="tw" id="tw"></div>
    <div class="twsum" id="twsum"></div>
  </div>
</div>

<section>
  <h2>Who's in? <small>mark yourself for the next match so nobody has to run a poll</small></h2>
  <div class="avail" id="avail">
    <div class="av-tabs" id="av-tabs" role="tablist"></div>
    <div class="av-match" id="av-match"></div>
    <div class="av-rows" id="av-rows"></div>
    <div class="av-note" id="av-note">Loading availability…</div>
  </div>
</section>

<section>
  <h2>Our players <small>points, game record, and points by week (green = won the week)</small></h2>
  <div class="pgrid">{''.join(pcards)}</div>
  <div class="legend"><span><i style="background:var(--win)"></i>Won majority of games that week</span><span><i style="background:var(--loss)"></i>Lost majority</span><span><i style="background:var(--line)"></i>No games recorded</span></div>
</section>

<div class="two">
<section>
  <h2>Standings</h2>
  <div class="tblwrap"><table>
    <thead><tr><th></th><th>Team</th><th class="n">W</th><th class="n">L</th><th class="n">Pts</th><th class="n"></th></tr></thead>
    <tbody>{''.join(st_rows)}</tbody>
  </table></div>
</section>

<section>
  <h2>Our schedule <small>Mondays, 7:00 PM</small></h2>
  <ul class="sched collapsed" id="sched">{''.join(sc_rows)}</ul>
  <button class="showall" id="showall" type="button">Show full season</button>
</section>
</div>

<div class="two">
<section>
  <h2>League leaders <small>top 10 of {len(pstand)}</small></h2>
  <div class="tblwrap"><table>
    <thead><tr><th></th><th>Player</th><th class="n">Pts</th></tr></thead>
    <tbody>{ld_rows}</tbody>
  </table></div>
</section>

<section>
  <h2>Recent results</h2>
  {"<ul class='rlist'>" + ''.join(rr_rows) + "</ul>" if rr_rows else "<p class='muted'>No results posted yet.</p>"}
</section>
</div>

<section>
  <h2>League calendar <small>every match, all 10 teams · Mondays 7:00 PM</small></h2>
  <div class="cal-wrap" id="cal">
    <div class="cal-head">
      <div class="cal-nav"><button type="button" id="cal-prev" aria-label="Previous month">‹</button><span class="mn" id="cal-mn"></span><button type="button" id="cal-next" aria-label="Next month">›</button></div>
      <label class="cal-filter"><input type="checkbox" id="cal-only"> LPP2 games only</label>
    </div>
    {''.join(cal_months)}
    <div class="cal-legend"><span><i style="background:var(--brass)"></i>LPP2 upcoming</span><span><i style="background:var(--win)"></i>LPP2 win</span><span><i style="background:var(--loss)"></i>LPP2 loss (FF = forfeit)</span><span><i style="background:var(--pending)"></i>Played, score pending</span><span><i style="background:var(--rail);border:1px solid var(--line)"></i>Other matches (shown for upcoming dates only)</span><span><i style="border:1px solid var(--brass-2)"></i>Today</span></div>
  </div>
</section>

<dialog class="pmodal" id="pmodal" aria-labelledby="pm-name">
  <div class="pm-head"><div><h3 id="pm-name"></h3><div class="sum" id="pm-sum"></div></div><button type="button" class="pm-close" id="pm-close" aria-label="Close">✕</button></div>
  <div class="pm-body" id="pm-body"></div>
</dialog>

{captains_html}
{rules_html}

<footer>
  <span>Source: <a href="{SOURCE_URL}" target="_blank" rel="noopener">Shooters Pool League '26 on appleague.io</a></span>
  <span>Roster: {esc(', '.join(p['name'] for p in sorted(players, key=lambda p: p['name'])))}</span>
</footer>
</div>

{script_js}
"""
# standalone document for GitHub Pages
head, body = page.split('<div class="wrap">', 1)
doc = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
       '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
       '<meta name="theme-color" content="#0f2a1f">'
       + head + '</head><body><div class="wrap">' + body + '</body></html>')
open(OUT, "w").write(doc)
print("built", OUT, len(page), "bytes;", "next:", next_match and next_match["label"], "| record", me["wins"], me["losses"])
