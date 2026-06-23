#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from EduFlowGraph.store.migration import MigrationValidationError, export_sqlite_storage


def main() -> int:
    parser = argparse.ArgumentParser(description="Export EduFlowGraph SQLite data to JSON")
    parser.add_argument("--database-path", type=Path, default=Path("data/eduflowgraph.db"))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = export_sqlite_storage(args.database_path, args.output_dir)
    except MigrationValidationError as exc:
        print(f"storage export failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
