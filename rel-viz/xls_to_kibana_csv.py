#!/usr/bin/env python3
"""Convert the relationship spreadsheet (.xls / .xlsx) into a Kibana-friendly
CSV (or NDJSON).

What it does:
  1. Reads the workbook with pandas (auto-selects engine by extension).
  2. Forward-fills columns that contain merged cells in the source XLS — by
     default just `Entity` (column A) which is merged across each entity block
     in the source spreadsheet. Add more with `--ffill "Col One,Col Two"`.
  3. Explodes comma-separated columns into one row per token. By default this
     covers the two columns we know carry lists in this dataset:
        * Base BDE Dependancy  (col E)
        * Parallel lookup      (col G)
     Override with `--explode "Col,Other Col"`.
  4. Normalises headers to snake_case so Elasticsearch field names are clean.
  5. Drops fully empty rows and writes UTF-8 (no BOM).
  6. Optional `--add-timestamp` injects an `@timestamp` field at ingest time
     so Kibana auto-detects this as a time-series source.

Output formats:
  * `--format csv` (default) — for Logstash csv filter or Kibana Data Visualizer.
  * `--format ndjson`        — newline-delimited JSON, ready for the
                                Elasticsearch `_bulk` API or Kibana
                                Filebeat ingest.

Example:
    python xls_to_kibana_csv.py relationship.xlsx
    python xls_to_kibana_csv.py /path/to/main.xls -o out.csv --add-timestamp
    python xls_to_kibana_csv.py main.xlsx --format ndjson --explode "Parallel lookup"
    python xls_to_kibana_csv.py main.xlsx --sheet "Relationships"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

DEFAULT_FFILL = ["Entity", "Base Bde Time travel status"]
DEFAULT_EXPLODE = ["Base BDE Dependancy", "Parallel lookup"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def snake_case(name: str) -> str:
    """`Base BDE Dependancy` → `base_bde_dependancy`."""
    s = re.sub(r"[^\w\s]", "", str(name))
    s = re.sub(r"\s+", "_", s.strip())
    return s.lower()


def split_comma(value) -> list[str]:
    """Split a comma-separated cell into trimmed non-empty tokens.

    Treats `N/A`, empty strings, NaN as a single empty token so the row is
    preserved by `explode()` rather than dropped.
    """
    if pd.isna(value):
        return [""]
    text = str(value).strip()
    if not text or text.upper() == "N/A":
        return [""]
    parts = [t.strip() for t in text.split(",")]
    return [t for t in parts if t] or [""]


def find_column(df: pd.DataFrame, name: str) -> str | None:
    """Case-insensitive column lookup; returns the actual column name or None."""
    lower = {c.lower(): c for c in df.columns}
    return lower.get(name.lower())


# ---------------------------------------------------------------------------
# Core transform
# ---------------------------------------------------------------------------
def transform(
    df: pd.DataFrame,
    ffill_cols: list[str],
    explode_cols: list[str],
    add_timestamp: bool,
) -> pd.DataFrame:
    df = df.copy()

    # Forward-fill columns that come from merged cells.
    for col_name in ffill_cols:
        actual = find_column(df, col_name)
        if actual is None:
            print(f"  [warn] ffill column not found: {col_name!r}", file=sys.stderr)
            continue
        df[actual] = df[actual].ffill()

    # Drop rows that are completely empty (all NaN).
    df = df.dropna(how="all").reset_index(drop=True)

    # Explode comma-separated columns one at a time. Splitting first turns
    # the cell into a list, then `.explode()` fans it across rows.
    for col_name in explode_cols:
        actual = find_column(df, col_name)
        if actual is None:
            print(f"  [warn] explode column not found: {col_name!r}", file=sys.stderr)
            continue
        df[actual] = df[actual].apply(split_comma)
        df = df.explode(actual, ignore_index=True)
        # Replace the placeholder empty string with NaN for cleaner JSON/CSV.
        df[actual] = df[actual].replace("", pd.NA)

    # Trim string fields and normalise NaN representation.
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(
                lambda v: v.strip() if isinstance(v, str) else v
            )
            df[col] = df[col].replace({"": pd.NA, "N/A": pd.NA, "n/a": pd.NA})

    # Snake-case headers.
    df.columns = [snake_case(c) for c in df.columns]

    if add_timestamp:
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        df.insert(0, "@timestamp", ts)

    return df


# ---------------------------------------------------------------------------
# IO
# ---------------------------------------------------------------------------
def read_workbook(path: Path, sheet: str | int | None) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix not in (".xls", ".xlsx", ".xlsm"):
        raise SystemExit(f"Unsupported file type: {suffix}. Use .xls or .xlsx")

    # pandas picks openpyxl for .xlsx and xlrd (older versions) for .xls.
    # If xlrd isn't installed for .xls, surface a clear hint.
    try:
        return pd.read_excel(path, sheet_name=sheet if sheet is not None else 0)
    except ImportError as exc:
        if suffix == ".xls":
            raise SystemExit(
                "Reading .xls requires `xlrd<2.0`. Install with:  "
                "pip install 'xlrd<2.0'"
            ) from exc
        raise


def write_csv(df: pd.DataFrame, out: Path) -> None:
    df.to_csv(out, index=False, encoding="utf-8")


def write_ndjson(df: pd.DataFrame, out: Path) -> None:
    with out.open("w", encoding="utf-8") as fh:
        for record in df.to_dict(orient="records"):
            clean = {k: (None if pd.isna(v) else v) for k, v in record.items()}
            fh.write(json.dumps(clean, ensure_ascii=False, default=str))
            fh.write("\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Flatten the relationship workbook into a Kibana-friendly CSV/NDJSON."
    )
    p.add_argument("input", type=Path, help="Path to input .xls or .xlsx")
    p.add_argument(
        "-o", "--output", type=Path,
        help="Output path (default: input filename with .csv/.ndjson extension).",
    )
    p.add_argument(
        "--format", choices=("csv", "ndjson"), default="csv",
        help="Output format (default: csv).",
    )
    p.add_argument(
        "--sheet", default=None,
        help="Sheet name or 0-based index to read (default: first sheet).",
    )
    p.add_argument(
        "--ffill", default=",".join(DEFAULT_FFILL),
        help=f"Comma-separated columns to forward-fill "
             f"(default: {','.join(DEFAULT_FFILL)!r}). "
             "Use '' to disable.",
    )
    p.add_argument(
        "--explode", default=",".join(DEFAULT_EXPLODE),
        help=f"Comma-separated columns to fan out one row per token "
             f"(default: {','.join(DEFAULT_EXPLODE)!r}). "
             "Use '' to disable.",
    )
    p.add_argument(
        "--add-timestamp", action="store_true",
        help="Inject an `@timestamp` column with the current UTC time so Kibana "
             "treats this as a time-based index pattern.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if not args.input.exists():
        raise SystemExit(f"Input file not found: {args.input}")

    sheet: str | int | None = args.sheet
    if isinstance(sheet, str) and sheet.isdigit():
        sheet = int(sheet)

    out = args.output or args.input.with_suffix(
        ".csv" if args.format == "csv" else ".ndjson"
    )

    ffill_cols = [c.strip() for c in args.ffill.split(",") if c.strip()]
    explode_cols = [c.strip() for c in args.explode.split(",") if c.strip()]

    print(f"▸ Reading  {args.input}  (sheet={sheet if sheet is not None else 0})")
    df_raw = read_workbook(args.input, sheet)
    print(f"  {len(df_raw)} raw rows, {len(df_raw.columns)} columns: {list(df_raw.columns)}")

    df = transform(df_raw, ffill_cols, explode_cols, args.add_timestamp)
    print(f"▸ Transformed → {len(df)} rows, columns: {list(df.columns)}")

    print(f"▸ Writing  {out}  (format={args.format})")
    if args.format == "csv":
        write_csv(df, out)
    else:
        write_ndjson(df, out)

    print(f"✔ Done. {out.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
