# lpp2-pool

Lincoln Park Pub 2 team site for Shooters Pool League '26: standings, schedule, player stats, availability, and rules. Auto-refreshes from appleague.io.

**Live site:** https://jakevanderkar3434.github.io/lpp2-pool/

## How it works
- `src/fetch_league.py` downloads the league page and extracts its embedded JSON.
- `src/build.py` turns that into `index.html` (plus `src/history.json`, an accumulated results log).
- `.github/workflows/refresh.yml` runs both on a schedule (Tue 6 PM, Wed 9 AM ET) and commits the result. GitHub Pages serves `index.html` from `main`.
- `src/overrides.json` holds manual corrections (forfeits, missing scores).
- `src/config.json` holds the Google Apps Script URL for the "Who's in?" availability board. `src/avail_apps_script.gs` is the script to deploy.

## Manual refresh
Actions tab → "Refresh league data" → Run workflow.
