#!/usr/bin/env python3
"""Reset the digital twin to its clean, seeded state.

The twin runs the same app and database as the bookstore (TWIN_URL points at the
backend itself), so a reset wipes every table and re-seeds the deterministic
synthetic dataset. Demo flow: Run attack -> Fix -> Replay -> reset -> repeat.

Usage (from the repo root):
    python scripts/reset_twin.py            # asks for confirmation
    python scripts/reset_twin.py --yes      # no prompt
    python scripts/reset_twin.py --docker   # reset the database inside the running container
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend-python"


def _reset_in_docker() -> int:
    cmd = ["docker", "compose", "exec", "-T", "backend", "python", "app/db/seed.py", "--reset"]
    try:
        return subprocess.run(cmd, cwd=REPO_ROOT, check=False).returncode
    except FileNotFoundError:
        print("error: docker is not installed or not on PATH", file=sys.stderr)
        return 1


def _reset_local(seed: int | None, assume_yes: bool) -> int:
    # Same trick as generate_report.py: the default sqlite path is relative to backend-python/.
    os.chdir(BACKEND_DIR)
    sys.path.insert(0, str(BACKEND_DIR))

    from sqlmodel import Session  # noqa: E402

    from app.db.seed import dataset_fingerprint, seed_database  # noqa: E402
    from app.db.session import engine, init_db  # noqa: E402

    target = engine.url.render_as_string(hide_password=True)
    if not assume_yes:
        answer = input(f"This deletes ALL rows in {target} and re-seeds it. Type 'reset' to continue: ")
        if answer.strip().lower() != "reset":
            print("Aborted. Nothing changed.")
            return 1

    init_db()
    with Session(engine) as session:
        counts = seed_database(session, reset=True, seed=seed)
        fingerprint = dataset_fingerprint(session)

    print(f"Twin reset: {target}")
    for name, count in (counts or {}).items():
        if count:
            print(f"  {name:<15}{count:>6}")
    print(f"  dataset fingerprint: {fingerprint}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reset the NIVARA digital twin.")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    parser.add_argument("--seed", type=int, help="override the dataset seed (local mode only)")
    parser.add_argument("--docker", action="store_true", help="reset inside the running docker compose backend")
    args = parser.parse_args(argv)

    if args.docker:
        if args.seed is not None:
            parser.error("--seed is not supported with --docker (the container uses its SEED env var)")
        return _reset_in_docker()
    return _reset_local(args.seed, args.yes)


if __name__ == "__main__":
    raise SystemExit(main())
