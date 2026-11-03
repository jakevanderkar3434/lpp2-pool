#!/usr/bin/env python3
"""Fetch Shooters Pool League '26 page, extract embedded DATA JSON, write league.json."""
import json, re, sys, urllib.request, datetime
URL = "https://shooterspool.appleague.io/league/41766977-7dfa-467e-b24f-91b2f8b5d5aa"
OUT = sys.argv[1] if len(sys.argv) > 1 else "league.json"
req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8")
m = re.search(r"var DATA = (\{.*?\});\s*\n", html, re.S)
if not m:
    i = html.index("var DATA = ") + len("var DATA = ")
    data, _ = json.JSONDecoder().raw_decode(html[i:])
else:
    data = json.loads(m.group(1))
data["fetched_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
json.dump(data, open(OUT, "w"))
print("ok", len(html), "bytes ->", OUT)
