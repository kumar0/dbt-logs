#!/usr/bin/env python3
"""Convert dbt-glue (PySpark/Iceberg) compiled SQL into runnable Athena SQL.

Given a dbt model folder name (e.g. ``order_transform``), this script:

1. Finds that folder under any ``target/run/`` directory in the project (the folder
   only exists after ``dbt run`` has compiled the models).
2. For every ``.sql`` file in the folder, strips the dbt materialization wrapper
   (``CREATE OR REPLACE TABLE ... AS`` / ``INSERT INTO ... SELECT``) down to a bare
   query, inlines any referenced sibling views (other ``.sql`` files in the same
   folder) as subqueries so the query is self-contained, then transpiles it from the
   Spark dialect to the Athena dialect with sqlglot.
3. Writes each result as ``ath_<original-name>.sql`` into ``athena_sql_version/``,
   mirroring the folder's path from ``target/run/`` downward.

Usage (run from the ``athena_sql_version`` folder)::

    python convert_to_athena.py <folder_name>

Requires ``sqlglot`` (``pip install sqlglot``).
"""

import argparse
import os
import re
import sys
from pathlib import Path

try:
    import sqlglot
except ImportError:
    sys.exit(
        "The 'sqlglot' library is required but not installed.\n"
        "Install it with:  pip install sqlglot"
    )


# dbt-glue points every reference at the 'glue_catalog' catalog; Athena uses the
# Glue Data Catalog as its default catalog, so the prefix must be dropped.
GLUE_CATALOG_RE = re.compile(r"\bglue_catalog\.", re.IGNORECASE)

# Leading "CREATE [OR REPLACE] TABLE ... [USING iceberg] [LOCATION '...'] AS" wrapper.
# Non-greedy up to the first standalone 'as' that introduces the CTAS body.
CREATE_AS_RE = re.compile(
    r"^\s*create\s+(?:or\s+replace\s+)?table\b.*?\bas\b\s*",
    re.IGNORECASE | re.DOTALL,
)

# Leading "INSERT INTO <table> [(cols)]" wrapper, up to the SELECT body.
INSERT_INTO_RE = re.compile(
    r"^\s*insert\s+into\s+[\w.]+\s*(?:\([^)]*\)\s*)?(?=select\b)",
    re.IGNORECASE | re.DOTALL,
)

# Cap recursion when inlining views that reference each other.
MAX_INLINE_DEPTH = 25


def strip_wrapper(sql: str) -> str:
    """Remove the dbt materialization wrapper, leaving a bare SELECT/WITH query."""
    stripped = CREATE_AS_RE.sub("", sql, count=1)
    if stripped != sql:
        return stripped.strip()
    stripped = INSERT_INTO_RE.sub("", sql, count=1)
    return stripped.strip()


def strip_catalog(sql: str) -> str:
    """Drop the 'glue_catalog.' catalog prefix from table references."""
    return GLUE_CATALOG_RE.sub("", sql)


def load_body(path: Path) -> str:
    """Read a compiled SQL file and reduce it to a bare, catalog-clean query body."""
    raw = path.read_text(encoding="utf-8")
    return strip_catalog(strip_wrapper(raw))


def inline_views(sql: str, views: dict, in_progress: frozenset, depth: int) -> str:
    """Recursively replace ``FROM/JOIN <view>`` references with the view's body.

    ``views`` maps a view stem (filename without ``.sql``) to its Path. Each matched
    reference is replaced by ``FROM/JOIN ( <inlined view body> )``; any trailing
    alias in the original SQL is preserved because the match stops at the table name.
    """
    if depth > MAX_INLINE_DEPTH:
        print(f"  ! max inline depth ({MAX_INLINE_DEPTH}) reached; leaving remaining refs")
        return sql

    for stem, path in views.items():
        if stem in in_progress:
            continue  # avoid cyclic self-reference
        # Match the view stem optionally qualified by schema/catalog parts.
        ref_re = re.compile(
            rf"\b(FROM|JOIN)\s+(?:[\w]+\.)*{re.escape(stem)}\b",
            re.IGNORECASE,
        )
        if not ref_re.search(sql):
            continue
        inner = inline_views(load_body(path), views, in_progress | {stem}, depth + 1)
        sql = ref_re.sub(lambda m: f"{m.group(1)} (\n{inner}\n)", sql)
    return sql


def convert_file(path: Path, views: dict) -> tuple[str, bool]:
    """Convert one compiled SQL file to Athena SQL.

    Returns (converted_sql, transpiled_ok). Inlining happens on the raw Spark SQL,
    then the fully-assembled query is transpiled once so dialect handling (notably
    date/time functions) is applied consistently.
    """
    body = load_body(path)
    inlined = inline_views(body, views, frozenset({path.stem}), 0)
    try:
        return sqlglot.transpile(inlined, read="spark", write="athena", pretty=True)[0], True
    except Exception as exc:  # noqa: BLE001 - never drop a file on a transpile error
        print(f"  ! sqlglot could not transpile {path.name}: {exc}")
        print("    -> writing inlined (pre-transpile) SQL instead")
        return inlined, False


def find_model_folder(project_root: Path, folder_name: str) -> list:
    """Find directories named ``folder_name`` located under a ``target/run/`` path."""
    matches = []
    for path in project_root.rglob(folder_name):
        if not path.is_dir():
            continue
        if "athena_sql_version" in path.parts:
            continue  # never treat our own output tree as a source
        parts = path.parts
        if any(
            parts[i] == "target" and parts[i + 1] == "run"
            for i in range(len(parts) - 1)
        ):
            matches.append(path)
    return matches


def mirror_output_dir(matched: Path, output_base: Path) -> Path:
    """Map a matched ``.../target/run/<...>/models/<...>/folder`` path to the output tree.

    Preserves everything after the ``models`` segment, e.g.
    ``.../target/run/dpiibc_prepared/models/avqdf/order_transform`` ->
    ``<base>/avqdf/order_transform``. If there is no ``models`` segment, falls back to
    everything from the ``run`` segment downward.
    """
    parts = matched.parts
    models_idxs = [i for i, p in enumerate(parts) if p == "models"]
    if models_idxs:
        start = models_idxs[-1] + 1
    else:
        start = next(
            i + 1
            for i in range(len(parts) - 1)
            if parts[i] == "target" and parts[i + 1] == "run"
        )
    return output_base.joinpath(*parts[start:])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert dbt-glue compiled Spark SQL to Athena SQL for a model folder."
    )
    parser.add_argument(
        "folder_name",
        help="Name of the compiled model folder under target/run (e.g. order_transform).",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent          # the athena_sql_version folder
    project_root = script_dir.parent

    matches = find_model_folder(project_root, args.folder_name)
    if not matches:
        print(
            f"Folder '{args.folder_name}' not found under any target/run/ directory.\n"
            f"Please run 'dbt run' for this model before running this script."
        )
        return 1
    if len(matches) > 1:
        print(f"Multiple folders named '{args.folder_name}' found:")
        for m in matches:
            print(f"  - {m}")
        print(f"Using the first match: {matches[0]}")
    source_dir = matches[0]

    sql_files = [
        p for p in sorted(source_dir.glob("*.sql")) if not p.name.startswith("ath_")
    ]
    if not sql_files:
        print(f"No .sql files found in {source_dir}")
        return 1

    # Every sibling .sql file is a candidate view that may be inlined.
    views = {p.stem: p for p in sql_files}

    output_dir = mirror_output_dir(source_dir, script_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Source : {source_dir}")
    print(f"Output : {output_dir}")
    print(f"Found {len(sql_files)} .sql file(s)\n")

    converted, fell_back = 0, []
    for path in sql_files:
        print(f"- {path.name}")
        athena_sql, ok = convert_file(path, views)
        out_path = output_dir / f"ath_{path.name}"
        out_path.write_text(athena_sql + "\n", encoding="utf-8")
        converted += 1
        if not ok:
            fell_back.append(path.name)

    print(f"\nDone. Converted {converted} file(s) into {output_dir}")
    if fell_back:
        print(f"  {len(fell_back)} file(s) fell back to pre-transpile SQL: {', '.join(fell_back)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
