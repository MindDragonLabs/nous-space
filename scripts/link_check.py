#!/usr/bin/env python3
"""Build-time link & health checker for the ecosystem catalog (flag-only).

Checks every URL in ecosystem.json plus a few key site links, and caches the
result in link_check.json. A cached result younger than 72 hours is reused.

Classification:
  ok       2xx/3xx
  dead     404 or 410 (the page is gone)
  unknown  anything else — timeouts, DNS errors, 429, 5xx, 403 — transient
           problems are never reported as dead

This script NEVER fails a build: every error is caught and it always exits 0.
It is polite: one request at a time, a fixed delay between requests, and a
per-run cap so a cold cache fills over several runs.

Usage:  python3 scripts/link_check.py [--max 300] [--delay 0.5] [--timeout 8]
build.py only reads link_check.json; run this script (or set
NOUS_LINK_CHECK=1 for build.py) to refresh it.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import socket
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE = ROOT / "link_check.json"
SOURCE = ROOT / "ecosystem.json"
CATEGORIES = ("plugins", "skills", "mods", "mcp", "tools")
KEY_LINKS = (
    "https://github.com/NousResearch/hermes-agent",
    "https://nous.minddragonlabs.com/api",
    "https://nous.minddragonlabs.com/llms.txt",
)
TTL = dt.timedelta(hours=72)
UA = "nous-space-link-check/1.0 (+https://nous.minddragonlabs.com/llms.txt)"


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def catalog_urls() -> list[str]:
    try:
        data = json.loads(SOURCE.read_text(encoding="utf-8"))
    except Exception:
        return list(KEY_LINKS)
    urls = set(KEY_LINKS)
    for cat in CATEGORIES:
        for item in data.get(cat) or []:
            if not isinstance(item, dict):
                continue
            url = item.get("url") or item.get("repo") or item.get("github_url") or item.get("docs_url")
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                urls.add(url)
    return sorted(urls)


def classify(code: int | None) -> str:
    if code is None:
        return "unknown"
    if 200 <= code < 400:
        return "ok"
    if code in (404, 410):
        return "dead"
    return "unknown"


def probe(url: str, timeout: float) -> tuple[str, int | None, str]:
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=method, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return classify(resp.status), resp.status, ""
        except urllib.error.HTTPError as err:
            if method == "HEAD" and err.code in (403, 405, 501):
                continue  # some hosts reject HEAD; retry once with GET
            return classify(err.code), err.code, ""
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as err:
            return "unknown", None, type(err).__name__
        except Exception as err:  # noqa: BLE001 — never fail
            return "unknown", None, type(err).__name__
    return "unknown", None, "no-response"


def load_cache() -> dict:
    try:
        data = json.loads(CACHE.read_text(encoding="utf-8"))
        if isinstance(data.get("results"), dict):
            return data
    except Exception:
        pass
    return {"results": {}}


def fresh(entry: dict, at: dt.datetime) -> bool:
    try:
        checked = dt.datetime.fromisoformat(str(entry.get("checked_at")).replace("Z", "+00:00"))
    except ValueError:
        return False
    return at - checked < TTL


def run(max_checks: int, delay: float, timeout: float) -> int:
    cache = load_cache()
    results: dict = cache["results"]
    urls = catalog_urls()
    at = now_utc()
    stale = [u for u in urls if not fresh(results.get(u) or {}, at)]
    todo = stale[:max_checks]
    print(f"link check: {len(urls)} urls, {len(urls) - len(stale)} cached (<72h), "
          f"checking {len(todo)} now (cap {max_checks})")
    for i, url in enumerate(todo):
        status, code, err = probe(url, timeout)
        prev = results.get(url) or {}
        # A single 404 after a previous ok is reported as unknown until it repeats.
        if status == "dead" and prev.get("status") == "ok":
            status = "unknown"
        results[url] = {"status": status, "code": code, "error": err,
                        "checked_at": now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")}
        if i + 1 < len(todo):
            time.sleep(delay)
    # drop entries for urls no longer in the catalog
    keep = set(urls)
    results = {u: results[u] for u in sorted(results) if u in keep}
    summary = {s: sum(1 for r in results.values() if r.get("status") == s) for s in ("ok", "dead", "unknown")}
    out = {"note": "Flag-only link health for the ecosystem explorer. dead = 404/410; "
                   "transient errors are unknown. Entries are reused for 72 hours.",
           "summary": summary, "results": results}
    text = json.dumps(out, indent=1, sort_keys=False) + "\n"
    try:
        if not CACHE.exists() or CACHE.read_text(encoding="utf-8") != text:
            tmp = CACHE.with_suffix(".json.tmp")
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(CACHE)
    except OSError as err:
        print(f"link check: could not write cache ({err})")
    print(f"link check: ok {summary['ok']} · dead {summary['dead']} · unknown {summary['unknown']}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--max", type=int, default=300, help="max URLs to check this run")
    ap.add_argument("--delay", type=float, default=0.5, help="seconds between requests")
    ap.add_argument("--timeout", type=float, default=8.0, help="per-request timeout")
    args = ap.parse_args()
    try:
        return run(max(0, args.max), max(0.0, args.delay), max(1.0, args.timeout))
    except Exception as err:  # noqa: BLE001 — flag-only, never fail the build
        print(f"link check: skipped ({type(err).__name__}: {err})")
        return 0


if __name__ == "__main__":
    sys.exit(main())
