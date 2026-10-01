#!/usr/bin/env python3
"""Advisory performance gate for the nous-space static site.

Prints a table of every payload the page loads (data shards, JS, HTML, feeds)
with raw and gzip sizes, flags any JSON shard over the 350 KB budget, and
estimates first paint from the critical path (index.html + render-blocking CSS;
all scripts are deferred).

Always exits 0 — warnings only. build.py runs it at the end of every build.

Usage:  python3 scripts/perf_gate.py
"""
from __future__ import annotations

import gzip
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHARD_BUDGET = 350 * 1024          # per JSON shard, raw bytes
HTML_BUDGET = 350 * 1024           # index.html, raw bytes (advisory)
# Network profiles for the first-paint estimate: (name, bytes/sec, round-trip s)
PROFILES = (("4G", 9_000_000 / 8, 0.170), ("slow 3G", 400_000 / 8, 0.400))
# The hugeicons stylesheet is the one render-blocking external resource; the
# vendored copy in the repo is the same file, so its size stands in for it.
BLOCKING_CSS = ("hgi-stroke-rounded.css",)
LAZY_JSON = ("news.json",)


def measure(path: pathlib.Path) -> tuple[int, int]:
    """(raw bytes, gzip -9 bytes) for one file; (0, 0) when missing."""
    try:
        raw = path.read_bytes()
    except OSError:
        return 0, 0
    return len(raw), len(gzip.compress(raw, 9, mtime=0))


def payloads(root: pathlib.Path) -> list[tuple[str, str]]:
    rows = [("index.html", "html")]
    rows += [(p.name, "js") for p in sorted(root.glob("*.js"))]
    rows += [(f"data/{p.name}", "shard") for p in sorted((root / "data").glob("*.json"))]
    rows += [(name, "lazy") for name in LAZY_JSON]
    rows += [("feed.json", "feed"), ("feed.xml", "feed")]
    return [(rel, kind) for rel, kind in rows if (root / rel).exists()]


def first_paint(root: pathlib.Path) -> list[tuple[str, float]]:
    _raw, html_gz = measure(root / "index.html")
    css_gz = sum(measure(root / name)[1] for name in BLOCKING_CSS)
    out = []
    for name, bps, rtt in PROFILES:
        # DNS+TCP+TLS ≈ 3 RTT for the document, +1 RTT for the CDN stylesheet
        seconds = 3 * rtt + html_gz / bps + (rtt + css_gz / bps if css_gz else 0)
        out.append((name, seconds))
    return out


def report(root: pathlib.Path = ROOT) -> int:
    warnings = []
    print(f"perf gate — budget {SHARD_BUDGET // 1024} KB per JSON shard (advisory, never fails)")
    print(f"  {'payload':<28} {'kind':<6} {'raw KB':>9} {'gzip KB':>9}  status")
    total_raw = total_gz = 0
    for rel, kind in payloads(root):
        raw, gz = measure(root / rel)
        total_raw += raw
        total_gz += gz
        budget = SHARD_BUDGET if kind in ("shard", "lazy") else HTML_BUDGET if kind == "html" else None
        status = "ok"
        if budget and raw > budget:
            status = "WARN over budget" + (" (loads on scroll only)" if kind == "lazy" else "")
            warnings.append(f"{rel} is {raw / 1024:,.1f} KB (> {budget // 1024} KB)")
        print(f"  {rel:<28} {kind:<6} {raw / 1024:>9,.1f} {gz / 1024:>9,.1f}  {status}")
    print(f"  {'total':<28} {'':<6} {total_raw / 1024:>9,.1f} {total_gz / 1024:>9,.1f}")
    estimates = ", ".join(f"{name} ≈ {sec:.2f}s" for name, sec in first_paint(root))
    print(f"  first paint estimate (index.html + blocking CSS, scripts deferred): {estimates}")
    for w in warnings:
        print(f"  warning: {w}")
    return 0


if __name__ == "__main__":
    report(ROOT)
    sys.exit(0)
