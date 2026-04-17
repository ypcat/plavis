# plavis — PLA Activity Visualizer

Interactive line chart of PLA aircraft and PLAN vessel activity around Taiwan,
built from the Ministry of National Defense (R.O.C.) daily bulletins at
<https://www.mnd.gov.tw/news/plaactlist/1>.

## What it does

- Crawls the MND bulletin list incrementally.
- Parses the Chinese (and English fallback) body text for daily totals:
  total aircraft sorties, median-line crossings, ADIZ quadrant counts,
  PLAN vessels, official ships.
- Best-effort OCR on the attached infographic for per-aircraft-type counts
  (J-10, J-16, Su-30, H-6, KJ-500, BZK-005, TB-001, …).
- Stores everything in a single wide CSV (`data/pla_activity.csv`) keyed by date.
- Renders `index.html`: a self-contained interactive Plotly page with a
  daily-totals line chart and a per-type stacked chart, range slider,
  and date-range buttons.

## Quick start

```bash
pip install -r requirements.txt
python update.py --since 2026-04-01 --no-ocr   # fast first run, totals only
open index.html
python update.py                                # incremental; OCR on by default
```

### CLI flags

- `--full` — ignore CSV, re-crawl every page.
- `--since YYYY-MM-DD` — stop crawling once an entry is older than this date.
- `--earliest YYYY-MM-DD` — hard floor (default `2020-09-01`).
- `--no-ocr` — skip infographic OCR (totals-only mode).
- `--ocr-backend paddle|tesseract` — override auto-detect.
- `--dry-run` — crawl + parse but don't write CSV/HTML.

## Data schema (`data/pla_activity.csv`)

```
date,source_id,total_aircraft,median_crossings,
sw_adiz,n_adiz,e_adiz,se_adiz,
plan_vessels,official_ships,
type_J-10,type_J-16,type_Su-30,type_H-6,type_KJ-500,type_BZK-005, ...
```

- One row per date (ISO `YYYY-MM-DD`), sorted ascending.
- `type_*` columns are added on-the-fly the first time a new airframe is seen.
- Missing fields are left empty (not zero) — OCR failures do not pollute totals.

## Automation

`.github/workflows/update.yml` runs `python update.py` daily at ~06:15 Taipei
(`22:15 UTC`), and commits any CSV/HTML diff back to the branch. Trigger
manually with "Run workflow".

`.github/workflows/pages.yml` publishes `index.html` + `data/` to GitHub
Pages whenever the update workflow finishes or anyone pushes to `main`.
To enable: **Settings → Pages → Build and deployment → Source: GitHub Actions**.
The site will be served at `https://ypcat.github.io/plavis/`.

## Source & caveats

- Primary source: MND PLA Activities list, `https://www.mnd.gov.tw/news/plaactlist/{page}`.
- From late January 2024 MND reduced the detail of its daily ADIZ reports;
  some older rows therefore have richer breakdowns than recent ones.
- OCR accuracy on the infographic is best-effort. The top-line totals chart
  never depends on OCR — it is parsed directly from the HTML body.
