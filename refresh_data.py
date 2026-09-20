#!/usr/bin/env python3
"""Cron entry point for the nous-space page — kept at this filename because the
5-minute job and nous_space_refresh.sh call it by name.

Real work lives in:
  fetch_state.py  -> state.json        (live data, scoped to the maintainer)
  build.py        -> index.html row    (render, between the BLOCKROW markers)

Usage:  python3 refresh_data.py [--dry-run]
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent
STEPS = ("fetch_state.py", "build.py")


def main() -> int:
    for step in STEPS:
        p = subprocess.run([sys.executable, str(ROOT / step)], capture_output=True, text=True)
        if p.returncode != 0:
            sys.stderr.write(f"{step} failed (exit {p.returncode}): {p.stderr.strip()[-400:]}\n")
            return p.returncode
        sys.stdout.write(p.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
