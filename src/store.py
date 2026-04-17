"""CSV read/write with date-keyed upsert and union-of-columns."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

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


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=BASE_COLUMNS)
    df = pd.read_csv(path, dtype={"source_id": "Int64"})
    for col in BASE_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    return df


def _order_columns(df: pd.DataFrame) -> list[str]:
    type_cols = sorted(c for c in df.columns if c.startswith("type_"))
    other = [c for c in df.columns if c not in BASE_COLUMNS and c not in type_cols]
    return BASE_COLUMNS + sorted(other) + type_cols


def upsert_rows(df: pd.DataFrame, rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return df
    new = pd.DataFrame(rows)
    combined = pd.concat([df, new], ignore_index=True, sort=False)
    # keep the *last* occurrence for each date (new rows overwrite old)
    combined = combined.drop_duplicates(subset=["date"], keep="last")
    combined = combined.sort_values("date", kind="stable").reset_index(drop=True)
    combined = combined[_order_columns(combined)]
    return combined


def save_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = df.copy()
    df = df[_order_columns(df)]
    # Write integer columns without trailing ``.0`` and keep NaN as empty.
    for col in df.columns:
        if col in ("date",):
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            df[col] = df[col].astype("Int64")
    df.to_csv(path, index=False)
