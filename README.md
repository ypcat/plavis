# plavis — PLA Activity Visualizer

Interactive line chart of PLA aircraft and PLAN vessel activity around Taiwan,
built from the Ministry of National Defense (R.O.C.) daily bulletins at
<https://www.mnd.gov.tw/news/plaactlist/1>.

## What it does

- Crawls the MND bulletin list incrementally.
- Parses the Chinese (and English fallback) body text for daily totals:
  total aircraft sorties, median-line crossings, ADIZ quadrant counts,
  PLAN vessels, official ships.
- Stores everything in a single CSV (`data/pla_activity.csv`) keyed by date.
- Renders `index.html`: a self-contained interactive Plotly page with a
  daily-totals line chart, range slider, and date-range buttons.

## Quick start

```bash
pip install -r requirements.txt
python update.py --since 2026-04-01
open index.html
```

### CLI flags

- `--full` — ignore CSV, re-crawl every page.
- `--since YYYY-MM-DD` — stop crawling once an entry is older than this date.
- `--earliest YYYY-MM-DD` — hard floor (default `2020-09-01`).
- `--dry-run` — crawl + parse but don't write CSV/HTML.
- `--debug-dump DIR` — dump raw HTML of empty pages for inspection.
- `-v`/`--verbose` — debug-level logging.

## Dependencies

Just `requests` + `beautifulsoup4`. No pandas, no OCR, no lxml.

## Data schema (`data/pla_activity.csv`)

```
date,source_id,total_aircraft,median_crossings,
sw_adiz,n_adiz,e_adiz,se_adiz,
plan_vessels,official_ships
```

- One row per date (ISO `YYYY-MM-DD`), sorted ascending.
- Missing fields are left empty (not zero).

## Automation

`.github/workflows/update.yml` runs `python update.py` daily at ~06:15 Taipei
(`22:15 UTC`) and commits any CSV/HTML diff back to `main`. Trigger manually
with **Run workflow**. The run always uploads `update.log` + any `debug/`
dumps as an artifact so empty crawls can be diagnosed.

`.github/workflows/pages.yml` publishes `index.html` + `data/` to GitHub
Pages whenever the update workflow finishes or anyone pushes to `main`.
To enable: **Settings → Pages → Build and deployment → Source: GitHub Actions**.
The site will be served at `https://ypcat.github.io/plavis/`.

## Source & caveats

- Primary source: MND PLA Activities list, `https://www.mnd.gov.tw/news/plaactlist/{page}`.
- From late January 2024 MND reduced the detail of its daily ADIZ reports;
  some older rows therefore have richer per-quadrant breakdowns than recent ones.
