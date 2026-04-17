"""Render the static Plotly dashboard from the in-memory CSV rows. Stdlib only."""

from __future__ import annotations

import io
from csv import DictWriter
from datetime import datetime, timezone
from pathlib import Path

from src.store import _order_columns, BASE_COLUMNS

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "templates" / "index.html.j2"


def _rows_to_csv_text(rows: dict[str, dict]) -> str:
    """Serialize the ``{date: {col: value}}`` mapping back to CSV text."""
    all_cols: set[str] = set(BASE_COLUMNS)
    for r in rows.values():
        all_cols.update(r.keys())
    cols = _order_columns(all_cols)
    buf = io.StringIO()
    w = DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for d in sorted(rows):
        r = rows[d]
        w.writerow({c: r.get(c, "") for c in cols})
    return buf.getvalue()


def build_html(rows: dict[str, dict], out_path: Path) -> None:
    csv_text = _rows_to_csv_text(rows)
    latest = max(rows) if rows else "—"
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

    tmpl = TEMPLATE_PATH.read_text(encoding="utf-8")
    html = (
        tmpl.replace("{{ csv_text }}", csv_text)
            .replace("{{ n_rows }}", str(len(rows)))
            .replace("{{ latest_date }}", latest)
            .replace("{{ generated_at }}", generated)
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
