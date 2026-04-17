"""Render the static Plotly dashboard from the CSV."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = ROOT / "templates"


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "xml"]),
    )


def build_html(df: pd.DataFrame, out_path: Path) -> None:
    df = df.sort_values("date", kind="stable").reset_index(drop=True)
    csv_text = df.to_csv(index=False)
    latest = df["date"].iloc[-1] if len(df) else "—"
    html = _env().get_template("index.html.j2").render(
        csv_text=csv_text,
        n_rows=len(df),
        latest_date=latest,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
