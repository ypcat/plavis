"""CSV read/write with date-keyed upsert and union-of-columns. Stdlib only."""

from __future__ import annotations

import csv
from pathlib import Path

BASE_COLUMNS = [
    "date",
    "source_id",
    "total_aircraft",
    "median_crossings",
    "sw_adiz",
    "n_adiz",
    "e_adiz",
    "se_adiz",
    "plan_vessels",
    "official_ships",
]


def load(path: Path) -> dict[str, dict[str, str]]:
    """Return ``{date: {column: value}}``; empty dict if the file is missing."""
    if not path.exists():
        return {}
    rows: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            d = (row.get("date") or "").strip()
            if not d:
                continue
            # drop empty-string fields so column-union is predictable
            rows[d] = {k: v for k, v in row.items() if v not in (None, "")}
    return rows


def upsert(existing: dict[str, dict], new_rows: list[dict]) -> dict[str, dict]:
    """Merge ``new_rows`` into ``existing``. For a given date, new values
    overwrite old values cell-by-cell; ``None``/``""`` in new rows do not
    erase existing data."""
    for r in new_rows:
        d = r.get("date")
        if not d:
            continue
        cleaned = {k: v for k, v in r.items() if v not in (None, "")}
        if d in existing:
            existing[d].update(cleaned)
        else:
            existing[d] = cleaned
    return existing


def _order_columns(all_cols: set[str]) -> list[str]:
    type_cols = sorted(c for c in all_cols if c.startswith("type_"))
    other = sorted(c for c in all_cols if c not in BASE_COLUMNS and not c.startswith("type_"))
    return BASE_COLUMNS + other + type_cols


def save(rows: dict[str, dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    all_cols: set[str] = set(BASE_COLUMNS)
    for r in rows.values():
        all_cols.update(r.keys())
    cols = _order_columns(all_cols)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for d in sorted(rows):
            row = rows[d]
            w.writerow({c: row.get(c, "") for c in cols})


def row_count(rows: dict) -> int:
    return len(rows)


def latest_date(rows: dict) -> str | None:
    return max(rows) if rows else None
