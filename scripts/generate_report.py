#!/usr/bin/env python3
"""Generate a NIVARA security report for one lab run.

Usage (from the repo root):
    python scripts/generate_report.py RUN_ID                      # JSON to stdout
    python scripts/generate_report.py RUN_ID -f html -o out.html  # HTML to a file
    python scripts/generate_report.py RUN_ID --save               # also store it in the DB

Uses the same functions M2's /api/reports routes call, so the CLI output and
the API output always match. Reads DATABASE_URL like the backend does.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

START_DIR = Path.cwd()  # remember where the user ran the command
REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend-python"


def _bootstrap_backend() -> None:
    # The default DATABASE_URL (sqlite:///./data/bookstore.db) is relative, so
    # run from backend-python/ exactly like the Docker image does (WORKDIR /app).
    os.chdir(BACKEND_DIR)
    sys.path.insert(0, str(BACKEND_DIR))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a NIVARA security report.")
    parser.add_argument("run_id", help="lab run id (as returned by /api/lab/run/<scenario>)")
    parser.add_argument("-f", "--format", choices=["json", "html"], default="json")
    parser.add_argument("-o", "--output", help="write to this file instead of stdout")
    parser.add_argument("--save", action="store_true", help="also persist the report in the database")
    args = parser.parse_args(argv)

    _bootstrap_backend()
    from sqlmodel import Session  # noqa: E402  (after sys.path/cwd setup)

    from app.db.session import engine, init_db  # noqa: E402
    from app.security.report_generator import (  # noqa: E402
        generate_html_report,
        generate_json_report,
        save_report,
    )

    init_db()
    try:
        with Session(engine) as db:
            if args.format == "html":
                content = generate_html_report(args.run_id, db)
            else:
                content = json.dumps(generate_json_report(args.run_id, db), indent=2, default=str)

            report_id = save_report(args.run_id, args.format, db) if args.save else None
    except Exception as exc:  # noqa: BLE001 - CLI boundary: report any failure cleanly
        print(f"error: could not generate report for run '{args.run_id}': {exc}", file=sys.stderr)
        return 1

    if args.output:
        out = Path(args.output)
        if not out.is_absolute():
            out = START_DIR / out  # relative to where you ran the command
        out.write_text(content, encoding="utf-8")
        print(f"Wrote {args.format} report to {out}", file=sys.stderr)
    else:
        print(content)

    if args.save:
        print(f"Saved report (id={report_id})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
