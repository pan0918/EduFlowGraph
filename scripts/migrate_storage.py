#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from EduFlowGraph.store.migration import MigrationValidationError, migrate_legacy_storage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Migrate EduFlowGraph JSON storage to SQLite")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--database-path", type=Path)
    parser.add_argument(
        "--replace-empty",
        action="store_true",
        help="Replace an initialized database only when all business tables are empty",
    )
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--dry-run", action="store_true")
    modes.add_argument("--apply", action="store_true")
    modes.add_argument("--verify", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    mode = "apply" if args.apply else "verify" if args.verify else "dry-run"
    database_path = args.database_path or args.data_dir / "eduflowgraph.db"
    try:
        report = migrate_legacy_storage(
            args.data_dir,
            database_path,
            mode=mode,
            replace_empty=args.replace_empty,
        )
    except MigrationValidationError as exc:
        print(f"migration validation failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
