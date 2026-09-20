#!/usr/bin/env python3
"""Fetch live PR state for the two nous-space clusters.

  pending (GREEN, left)  = OPEN PRs ranked by how likely they are to merge
  merged  (BLUE,  right) = recently MERGED PRs into the tracked branch

Writes state.json next to this file. No HTML is touched here.

Usage:  python3 fetch_state.py
Requires: gh CLI, authenticated.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import subprocess
import sys

REPO = "NousResearch/hermes-agent"
SOURCE_BRANCH = "main"
N_PENDING = 6
N_MERGED = 6

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "state.json"

OPEN_FIELDS = ("number,title,additions,deletions,changedFiles,commits,createdAt,updatedAt,"
               "isDraft,mergeable,reviewDecision,statusCheckRollup,author")
MERGED_FIELDS = "number,title,additions,deletions,changedFiles,commits,mergedAt,createdAt,author"


def gh(args: list[str]):
    p = subprocess.run(["gh"] + args, capture_output=True, text=True)
    if p.returncode != 0:
        print(f"gh failed: {p.stderr.strip()[:300]}", file=sys.stderr)
        raise SystemExit(2)
    return json.loads(p.stdout)


def parse(ts: str) -> dt.datetime:
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def age(ts: str, now: dt.datetime) -> tuple[int, str]:
    minutes = max(0, int(round((now - parse(ts)).total_seconds() / 60)))
    if minutes < 60:
        return minutes, f"~{minutes} min"
    hours = minutes / 60
    if hours < 48:
        return minutes, f"~{round(hours)} h"
    return minutes, f"~{round(hours / 24)} d"


def check_counts(rollup) -> tuple[int, int]:
    ok = total = 0
    for c in rollup or []:
        total += 1
        state = str(c.get("conclusion") or c.get("state") or "").upper()
        if state in ("SUCCESS", "NEUTRAL", "SKIPPED"):
            ok += 1
    return ok, total


def score_open(pr: dict, ok: int, total: int) -> int:
    """Deterministic 'is this about to land' score. Higher = closer to the divider."""
    s = 0
    review = (pr.get("reviewDecision") or "").upper()
    if review == "APPROVED":
        s += 4
    elif review == "CHANGES_REQUESTED":
        s -= 3
    if total and ok == total:
        s += 3
    elif total and ok / total >= 0.8:
        s += 2
    elif total and ok / total < 0.5:
        s -= 2
    mergeable = (pr.get("mergeable") or "").upper()
    if mergeable == "MERGEABLE":
        s += 2
    elif mergeable == "CONFLICTING":
        s -= 3
    if pr.get("isDraft"):
        s -= 4
    else:
        s += 1
    return s


def label_for(score: int, pr: dict, ok: int, total: int) -> str:
    if pr.get("isDraft"):
        return "draft"
    if score >= 9:
        state = "ready"
    elif score >= 6:
        state = "likely"
    elif score >= 3:
        state = "waiting"
    else:
        state = "blocked"
    checks = f"{ok}/{total} checks" if total else "no checks"
    return f"{state} · {checks}"


def norm_pending(pr: dict, now: dt.datetime) -> dict:
    ok, total = check_counts(pr.get("statusCheckRollup"))
    score = score_open(pr, ok, total)
    minutes, ago = age(pr.get("updatedAt") or pr["createdAt"], now)
    return {
        "number": pr["number"],
        "title": " ".join((pr.get("title") or "").split()),
        "additions": pr.get("additions", 0),
        "deletions": pr.get("deletions", 0),
        "changedFiles": pr.get("changedFiles", 0),
        "commits": len(pr.get("commits") or []),
        "author": (pr.get("author") or {}).get("login", ""),
        "age_min": minutes,
        "ago": ago,
        "checks_ok": ok,
        "checks_total": total,
        "review": pr.get("reviewDecision") or "",
        "mergeable": pr.get("mergeable") or "",
        "draft": bool(pr.get("isDraft")),
        "score": score,
        "label": label_for(score, pr, ok, total),
        "url": f"https://github.com/{REPO}/pull/{pr['number']}",
    }


def norm_merged(pr: dict, now: dt.datetime) -> dict:
    minutes, ago = age(pr["mergedAt"], now)
    return {
        "number": pr["number"],
        "title": " ".join((pr.get("title") or "").split()),
        "additions": pr.get("additions", 0),
        "deletions": pr.get("deletions", 0),
        "changedFiles": pr.get("changedFiles", 0),
        "commits": len(pr.get("commits") or []),
        "author": (pr.get("author") or {}).get("login", ""),
        "age_min": minutes,
        "ago": ago,
        "url": f"https://github.com/{REPO}/pull/{pr['number']}",
    }


def main() -> int:
    now = dt.datetime.now(dt.UTC)

    # notes: `commits` pulls a commit-authors connection; the GitHub node budget is
    # ~500k nodes, so keep the open-PR page at 30 (40+ trips the GraphQL limit).
    open_prs = gh(["pr", "list", "-R", REPO, "--state", "open", "--limit", "30",
                   "--base", SOURCE_BRANCH, "--json", OPEN_FIELDS])
    pending = sorted((norm_pending(p, now) for p in open_prs),
                     key=lambda p: (-p["score"], -p["age_min"]))[:N_PENDING]

    merged_prs = [p for p in gh(["pr", "list", "-R", REPO, "--state", "merged", "--limit", "40",
                                 "--base", SOURCE_BRANCH, "--json", MERGED_FIELDS]) if p.get("mergedAt")]
    merged_prs.sort(key=lambda p: p["mergedAt"], reverse=True)
    merged = [norm_merged(p, now) for p in merged_prs[:N_MERGED]]

    state = {
        "generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo": REPO,
        "branch": SOURCE_BRANCH,
        "open_total": len(open_prs),
        "pending": pending,
        "merged": merged,
    }
    OUT.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT.name}: {len(pending)} pending / {len(merged)} merged "
          f"(of {len(open_prs)} open) at {state['generated']}")
    for p in pending:
        print(f"  GREEN #{p['number']:<7} score={p['score']:<3} {p['label']:<20} {p['ago']:<7} {p['title'][:44]}")
    for m in merged:
        print(f"  BLUE  #{m['number']:<7} {m['ago']:<7} {m['author'][:14]:<14} {m['title'][:44]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
