#!/usr/bin/env python3
"""LaunchAgent entry point for the nous-space page — kept at this filename because
nous_space_refresh.sh calls it by name.

Real work lives in:
  fetch_state.py  -> state.json        (live data, scoped to the maintainer)
  build.py        -> index.html row    (render, between the BLOCKROW markers)

Usage:  python3 refresh_data.py [--dry-run]
"""
from __future__ import annotations

import os
import pathlib
import signal
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent
STEPS = (("fetch_state.py", 240), ("build.py", 60))


def run_step(step: str, timeout: int) -> int:
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / step)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(timeout=5)
        sys.stderr.write(f"{step} timed out after {timeout}s\n")
        return 2
    if stderr:
        sys.stderr.write(stderr)
    if proc.returncode != 0:
        sys.stderr.write(f"{step} failed (exit {proc.returncode})\n")
        return proc.returncode or 1
    sys.stdout.write(stdout or "")
    return 0


def main() -> int:
    for step, timeout in STEPS:
        status = run_step(step, timeout)
        if status != 0:
            return status
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
