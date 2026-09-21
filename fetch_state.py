#!/usr/bin/env python3
"""Fetch live PR state for the two nous-space clusters plus below-row panels.

  pending (GREEN, left)  = OPEN PRs the maintainer is involved in, ranked by how
                           likely they are to merge
  merged  (BLUE,  right) = PRs merged to the tracked branch by (or authored by)
                           the maintainer, newest first
  backlog      = aggregate open-PR stats (age buckets, area breakdown)
  releases     = recent release cadence
  merge_velo   = per-area merge velocity from the last ~40 merges

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
MAINTAINER = "teknium1"
N_PENDING = 6
N_MERGED = 35  # enough to overflow any screen and make the strip scrollable
OPEN_LIMIT = 30

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "state.json"

OPEN_FIELDS = ("number,title,additions,deletions,changedFiles,commits,createdAt,updatedAt,"
               "isDraft,mergeable,reviewDecision,statusCheckRollup,author")
MERGED_FIELDS = ("number,title,additions,deletions,changedFiles,commits,mergedAt,createdAt,"
                 "author,mergedBy")


def gh(args: list[str]) -> object:
    p = subprocess.run(["gh"] + args, capture_output=True, text=True)
    if p.returncode != 0:
        print(f"gh failed: {p.stderr.strip()[:300]}", file=sys.stderr)
        raise SystemExit(2)
    return json.loads(p.stdout)


def open_prs() -> list[dict]:
    seen: dict[int, dict] = {}
    for extra in (["--author", MAINTAINER], ["--search", f"involves:{MAINTAINER}"]):
        for pr in gh(["pr", "list", "-R", REPO, "--state", "open", "--limit", str(OPEN_LIMIT),
                      "--base", SOURCE_BRANCH, "--json", OPEN_FIELDS] + extra):
            seen[pr["number"]] = pr
    return list(seen.values())


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
    author = (pr.get("author") or {}).get("login", "")
    return {
        "number": pr["number"],
        "title": " ".join((pr.get("title") or "").split()),
        "additions": pr.get("additions", 0),
        "deletions": pr.get("deletions", 0),
        "changedFiles": pr.get("changedFiles", 0),
        "commits": len(pr.get("commits") or []),
        "author": author,
        "mine": author == MAINTAINER,
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
    author = (pr.get("author") or {}).get("login", "")
    return {
        "number": pr["number"],
        "title": " ".join((pr.get("title") or "").split()),
        "additions": pr.get("additions", 0),
        "deletions": pr.get("deletions", 0),
        "changedFiles": pr.get("changedFiles", 0),
        "commits": len(pr.get("commits") or []),
        "author": author,
        "mine": author == MAINTAINER,
        "merged_by": (pr.get("mergedBy") or {}).get("login", ""),
        "age_min": minutes,
        "ago": ago,
        "url": f"https://github.com/{REPO}/pull/{pr['number']}",
    }


# ── panel data ──────────────────────────────────────────────────────────────

def backlog_stats() -> dict:
    """Open-PR stats: true oldest (asc query), newest + area breakdown (desc query)."""
    import re
    from collections import Counter

    now = dt.datetime.now(dt.UTC)
    areas: Counter[str] = Counter()

    # ── true oldest: asc query, first result ──
    oldest_pr: dict | None = None
    r = subprocess.run(
        ["gh", "api",
         f"search/issues?q=repo:{REPO}+is:pr+is:open+base:{SOURCE_BRANCH}"
         "&sort=created&order=asc&per_page=1"],
        capture_output=True, text=True)
    if r.returncode == 0:
        data = json.loads(r.stdout)
        items = data.get("items", [])
        total_open = data.get("total_count", 0)
        if items:
            p = items[0]
            oldest_pr = {"number": p["number"], "title": p.get("title", ""),
                         "created": p["created_at"],
                         "age_days": (now - parse(p["created_at"])).days}
    else:
        total_open = 0

    # ── newest + area breakdown: desc query, 500 most recent ──
    newest_pr: dict | None = None
    page = 1
    scanned = 0
    while page <= 5:
        r2 = subprocess.run(
            ["gh", "api",
             f"search/issues?q=repo:{REPO}+is:pr+is:open+base:{SOURCE_BRANCH}"
             f"&sort=created&order=desc&per_page=100&page={page}"],
            capture_output=True, text=True)
        if r2.returncode != 0:
            break
        data = json.loads(r2.stdout)
        items = data.get("items", [])
        if not items:
            break
        if newest_pr is None and page == 1:
            p = items[0]
            newest_pr = {"number": p["number"], "title": p.get("title", ""),
                         "created": p["created_at"],
                         "age_hours": round((now - parse(p["created_at"])).total_seconds() / 3600, 1)}
        for pr in items:
            scanned += 1
            m = re.match(r"^(\w+(\([^)]*\))?)!?:\s*", pr.get("title", ""))
            area = m.group(1) if m else "other"
            areas[area] += 1
        page += 1

    return {
        "total_open": total_open,
        "scanned": scanned,
        "areas": dict(areas.most_common(12)),
        "oldest_pr": oldest_pr,
        "newest_pr": newest_pr,
    }


def release_stats() -> dict:
    """Recent releases and cadence."""
    r = subprocess.run(
        ["gh", "release", "list", "-R", REPO, "--limit", "40",
         "--json", "tagName,name,publishedAt"],
        capture_output=True, text=True)
    if r.returncode != 0:
        return {"releases": [], "cadence_days": None, "error": r.stderr.strip()[:200]}
    rels = json.loads(r.stdout)
    now = dt.datetime.now(dt.UTC)
    recent = []
    for rel in rels:
        pub = parse(rel["publishedAt"])
        days_ago = (now - pub).days
        if days_ago <= 90:
            # name field: "Hermes Agent v0.21.3 (v2026.9.14)"
            # extract version like "v0.21.3"
            name = rel.get("name") or ""
            recent.append({"tag": rel["tagName"],
                           "version": name,
                           "date": rel["publishedAt"][:10],
                           "days_ago": days_ago})
    cadence = round(90 / len(recent), 1) if recent else None
    latest = recent[0] if recent else None
    return {"releases": recent, "cadence_days": cadence, "latest": latest}


def merge_rate() -> dict:
    """Merged PR counts in recent windows for PRs/day velocity."""
    now = dt.datetime.now(dt.UTC)
    windows = [
        ("7d", now - dt.timedelta(days=7)),
        ("30d", now - dt.timedelta(days=30)),
        ("90d", now - dt.timedelta(days=90)),
    ]
    rates = {}
    for label, cutoff in windows:
        ds = cutoff.strftime("%Y-%m-%d")
        r = subprocess.run(
            ["gh", "api",
             f"search/issues?q=repo:{REPO}+is:pr+is:merged+base:{SOURCE_BRANCH}+merged:>={ds}"
             "&per_page=1"],
            capture_output=True, text=True)
        if r.returncode == 0:
            data = json.loads(r.stdout)
            total = data.get("total_count", 0)
            days = int(label[:-1])
            rates[label] = {"count": total, "per_day": round(total / days, 1)}
        else:
            rates[label] = {"count": 0, "per_day": 0}
    return rates


def merge_velocity() -> dict:
    """Per-area merge velocity from last ~40 merges (hours)."""
    import re
    from collections import defaultdict

    r = subprocess.run(
        ["gh", "pr", "list", "-R", REPO, "--state", "merged", "--base",
         SOURCE_BRANCH, "--limit", "40", "--json",
         "title,mergedAt,createdAt"],
        capture_output=True, text=True)
    if r.returncode != 0:
        return {}
    prs = json.loads(r.stdout)
    areas: dict[str, list[float]] = defaultdict(list)
    for p in prs:
        t = p.get("title", "")
        m = re.match(r"^(\w+(\([^)]*\))?)!?:\s*", t)
        area = m.group(1) if m else "other"
        try:
            c = parse(p["createdAt"])
            mr = parse(p["mergedAt"])
            h = (mr - c).total_seconds() / 3600
            areas[area].append(h)
        except Exception:
            pass
    velo: dict[str, dict] = {}
    for a, vals in sorted(areas.items(), key=lambda x: -len(x[1])):
        avg = sum(vals) / len(vals)
        velo[a] = {"count": len(vals), "avg_hours": round(avg, 1)}
    return velo


# ── main ────────────────────────────────────────────────────────────────────

def main() -> int:
    now = dt.datetime.now(dt.UTC)

    pend_all = [norm_pending(p, now) for p in open_prs()]
    pending = sorted(pend_all, key=lambda p: (-p["score"], -p["age_min"]))[:N_PENDING]

    merged_all = [p for p in gh(["pr", "list", "-R", REPO, "--state", "merged",
                                 "--limit", "40", "--base", SOURCE_BRANCH,
                                 "--json", MERGED_FIELDS]) if p.get("mergedAt")]
    merged_all.sort(key=lambda p: p["mergedAt"], reverse=True)
    merged_lane = [p for p in merged_all
                   if (p.get("mergedBy") or {}).get("login") == MAINTAINER
                   or (p.get("author") or {}).get("login") == MAINTAINER]
    merged = [norm_merged(p, now) for p in merged_lane[:N_MERGED]]

    state = {
        "generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo": REPO,
        "branch": SOURCE_BRANCH,
        "maintainer": MAINTAINER,
        "open_in_maintainer_lane": len(pend_all),
        "merged_scanned": len(merged_all),
        "pending": pending,
        "merged": merged,
        "backlog": backlog_stats(),
        "releases": release_stats(),
        "merge_velocity": merge_velocity(),
        "merge_rate": merge_rate(),
    }
    OUT.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT.name}: {len(pending)} pending / {len(merged)} merged "
          f"(maintainer lane: {len(pend_all)} open; {len(merged_all)} merges "
          f"scanned) at {state['generated']}")
    for p in pending:
        print(f"  GREEN #{p['number']:<7} score={p['score']:<3} {p['label']:<20} "
              f"{p['ago']:<7} {p['title'][:46]}")
    for m in merged:
        print(f"  BLUE  #{m['number']:<7} {m['ago']:<7} by {m['author'][:14]:<14} "
              f"{m['title'][:44]}")
    bl = state["backlog"]
    print(f"  BACKLOG {bl['total_open']} open · oldest #{bl['oldest_pr']['number']} "
          f"({bl['oldest_pr']['age_days']}d) · areas={dict(list(bl['areas'].items())[:6])}")
    rl = state["releases"]
    print(f"  RELEASES {len(rl['releases'])} in 90d · cadence ~{rl['cadence_days']}d"
          if rl["cadence_days"] else "  RELEASES N/A")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())