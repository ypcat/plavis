"""Update the PLA-activity dataset and regenerate index.html.

Typical use:

    python update.py                      # incremental, OCR on
    python update.py --no-ocr             # totals only
    python update.py --since 2026-01-01   # hard floor for this run
    python update.py --full               # walk until list exhausted
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path

from src import crawler, ocr, parser, render, store

ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "data" / "pla_activity.csv"
HTML_PATH = ROOT / "index.html"
DEFAULT_EARLIEST = date(2020, 9, 1)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--full", action="store_true", help="ignore CSV, crawl everything")
    p.add_argument("--since", type=_parse_date, default=None, help="stop once older than YYYY-MM-DD")
    p.add_argument("--earliest", type=_parse_date, default=DEFAULT_EARLIEST,
                   help=f"absolute floor (default {DEFAULT_EARLIEST})")
    p.add_argument("--no-ocr", action="store_true", help="skip infographic OCR")
    p.add_argument("--ocr-backend", choices=["paddle", "tesseract"], default=None)
    p.add_argument("--max-pages", type=int, default=500)
    p.add_argument("--dry-run", action="store_true", help="don't write CSV/HTML")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _build_row(detail: crawler.Detail, totals: parser.Totals, types: dict[str, int]) -> dict:
    row: dict = {
        "date": detail.date.isoformat() if detail.date else None,
        "source_id": detail.id,
    }
    row.update(totals.as_dict())
    for k, v in types.items():
        row[f"type_{k}"] = v
    return row


def main() -> int:
    args = _parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("update")

    df = store.load_csv(CSV_PATH)

    known_ids: set[int] = set()
    if not args.full and "source_id" in df.columns:
        known_ids = {int(x) for x in df["source_id"].dropna().astype(int).tolist()}

    floor = args.earliest
    if args.since and (floor is None or args.since > floor):
        floor = args.since

    session = crawler.new_session()

    new_rows: list[dict] = []
    seen = 0
    for entry in crawler.iter_entries(
        session,
        stop_ids=known_ids,
        earliest=floor,
        max_pages=args.max_pages,
    ):
        seen += 1
        log.info("fetching %s (%s) — %s", entry.id, entry.date, entry.title[:80])
        try:
            detail = crawler.fetch_detail(entry.id, session)
        except Exception as e:
            log.warning("detail fetch failed for %s: %s", entry.id, e)
            continue
        if detail.date is None and entry.date is not None:
            detail.date = entry.date
        if detail.date is None:
            log.warning("no date for %s — skipping", entry.id)
            continue

        totals = parser.parse_body(detail.body_text)

        types: dict[str, int] = {}
        if not args.no_ocr and detail.image_urls:
            img_url = detail.image_urls[0]
            try:
                img_bytes = crawler.download_image(img_url, session)
                types = ocr.extract_type_counts_from_image(img_bytes, backend=args.ocr_backend)
                if types:
                    log.info("  types: %s", types)
            except Exception as e:
                log.warning("  OCR failed for %s: %s", img_url, e)

        new_rows.append(_build_row(detail, totals, types))
        time.sleep(0.5)

    log.info("crawled %d entries, collected %d rows", seen, len(new_rows))

    if args.dry_run:
        for r in new_rows[-5:]:
            log.info("row: %s", r)
        return 0

    df2 = store.upsert_rows(df, new_rows)
    store.save_csv(df2, CSV_PATH)
    render.build_html(df2, HTML_PATH)

    if len(new_rows) == 0:
        log.info("no new rows; CSV/HTML regenerated")
    else:
        dates = sorted(r["date"] for r in new_rows if r.get("date"))
        log.info("added %d rows, dates %s…%s", len(new_rows), dates[0], dates[-1])
    return 0


if __name__ == "__main__":
    sys.exit(main())
