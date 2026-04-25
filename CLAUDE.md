# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv pip install -r requirements.txt    # only deps: requests, beautifulsoup4
python update.py --since 2026-04-01   # incremental crawl + regenerate index.html
python update.py --full               # ignore CSV, walk every list page
python update.py --dry-run -v         # crawl + parse, no writes, debug logging
python update.py --debug-dump debug/  # save raw HTML of empty list pages
```

There is no test suite, linter, or build step. `index.html` is the build output.

## Architecture

Single-shot pipeline driven by `update.py`:

1. `src.store.load(CSV_PATH)` → `{date: {col: val}}` dict from `data/pla_activity.csv`.
2. `src.crawler.iter_entries()` walks `mnd.gov.tw/news/plaactlist/{page}` from page 1, yielding `ListEntry` until it hits a known `source_id` (incremental) or runs out of pages older than `--earliest` floor (default 2020-09-01). Stops early after `grace_pages=3` consecutive pages with zero new IDs.
3. `src.crawler.fetch_detail(id)` pulls each `news/plaact/{id}` page and returns body text.
4. `src.parser.parse_body()` runs Chinese regexes first, English fallbacks second. Missing fields stay `None` (empty CSV cell, never zero). Quadrant regexes deliberately require `<quadrant>\s*N架次` adjacency — older bulletins listed quadrants with numbers, post-Jan-2024 ones list quadrants without numbers in the simplified summary, and we mustn't pick up the leading total.
5. `src.store.upsert()` merges new rows cell-by-cell — `None`/`""` never erases existing data, so a richer past row isn't downgraded by a later sparse re-crawl.
6. `src.store.save()` writes union-of-columns; `src.render.build_html()` substitutes `{{ csv_text }}` etc. into `templates/index.html.j2` (plain `str.replace`, not jinja). The CSV is embedded in the page as a `<script type="text/plain">`; Plotly.js loads from CDN and parses it client-side.

Key invariants:

- **Stdlib + 2 deps only.** No pandas, no jinja2, no lxml, no OCR. Don't add deps without strong justification.
- **Sparse data is the norm.** The CSV's column set grows with what MND publishes; old rows have richer ADIZ breakdowns than recent ones.
- **MND WAFs minimal HTTP clients.** `crawler.HEADERS` is a full desktop-Chrome header set; trimming it triggers 403s.
- **Empty crawl ≠ crash.** When a page returns no entries, `crawler._dump()` writes the raw HTML to `DEBUG_DUMP_DIR` and logs a 500-char text preview. Under GitHub Actions this is auto-enabled (`update.py` sets `DEBUG_DUMP_DIR = ROOT/"debug"` when `GITHUB_ACTIONS=true`); the workflow uploads it as the `crawler-debug-<run-id>` artifact.

## CI

Two workflows in `.github/workflows/`:

- `update.yml` — daily 22:15 UTC + `workflow_dispatch`. Two CI gotchas baked into this file: `astral-sh/setup-uv@v4` needs `enable-cache: false` *explicitly* (the default is `auto`, which still hard-errors when `uv.lock` is absent), and it doesn't install Python — `actions/setup-python@v5` must run before it so `uv pip install --system` finds a 3.11 interpreter. Runs `update.py --verbose`, uploads `update.log` + `debug/` as artifact, then commits `data/pla_activity.csv` + `index.html` if changed. The push step has a 5-attempt rebase-on-rejection loop because concurrent runs can collide.
- `pages.yml` — deploys `index.html` + `data/` to GitHub Pages on push to `main`, on `workflow_run` success of update, or manual dispatch.

Default branch must be `main`. Pages source must be set to "GitHub Actions" in repo settings.

## Date handling

`crawler._parse_date()` accepts both ROC民國 (`113/01/15`) and Western (`2024/01/15`) — years ≤200 are treated as ROC and offset by 1911.
