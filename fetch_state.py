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
import os
import pathlib
import re
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


def gh(args: list[str]):
    """Return parsed JSON, or None when gh times out or fails."""
    try:
        p = subprocess.run(["gh"] + args, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        print(f"gh timed out: {' '.join(args)[:80]}", file=sys.stderr)
        return None
    if p.returncode != 0:
        print(f"gh failed: {p.stderr.strip()[:300]}", file=sys.stderr)
        return None
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        print(f"gh returned invalid json: {' '.join(args)[:80]}", file=sys.stderr)
        return None


def open_prs() -> list[dict] | None:
    seen: dict[int, dict] = {}
    misses = 0
    for extra in (["--author", MAINTAINER], ["--search", f"involves:{MAINTAINER}"]):
        rows = gh(["pr", "list", "-R", REPO, "--state", "open", "--limit", str(OPEN_LIMIT),
                   "--base", SOURCE_BRANCH, "--json", OPEN_FIELDS] + extra)
        if not isinstance(rows, list):
            misses += 1
            continue
        for pr in rows:
            if isinstance(pr, dict) and pr.get("number") is not None:
                seen[pr["number"]] = pr
    if misses and not seen:
        return None
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
        "merged_at": pr.get("mergedAt") or "",
        "url": f"https://github.com/{REPO}/pull/{pr['number']}",
        "body": pr.get("body", ""),
        "images": _extract_images(pr.get("body", "")),
        "summary": _body_summary(pr.get("body", ""), pr.get("title", "")),
    }


def _extract_images(body: str) -> list[str]:
    """Pull image URLs from markdown body."""
    import re
    return re.findall(r'!\[.*?\]\(([^)]+)\)', body)


def _body_summary(body: str, title: str) -> str:
    """Extract a 1-2 sentence summary from PR body, or fall back to title."""
    import re
    if not body:
        title_clean = re.sub(r'^\w+(\([^)]*\))?!?:\\s*', '', title)
        return title_clean
    # Strip images
    text = re.sub(r'!\[.*?\]\([^)]+\)\n?', '', body)
    # Split on headings
    parts = re.split(r'\n#{1,3}\s+', text)
    first = parts[0].strip()
    if not first:
        return title
    # Take first 1-2 sentences from first paragraph
    sentences = re.split(r'(?<=[.!?])\s+', first)
    summary = ' '.join(sentences[:2])
    # Cap at ~200 chars
    if len(summary) > 200:
        summary = summary[:197] + "..."
    return summary


# ── panel data ──────────────────────────────────────────────────────────────

def backlog_stats() -> dict:
    """Open-PR stats: oldest/newest + daily new PR counts for chart."""
    import re
    from collections import Counter

    now = dt.datetime.now(dt.timezone.utc)
    areas: Counter[str] = Counter()
    today = now.date()

    # ── daily new PRs over last 7 days (GitHub search: created:YYYY-MM-DD) ──
    prev_daily = {
        row.get("date"): row
        for row in ((_previous_state().get("backlog") or {}).get("daily_new") or [])
        if isinstance(row, dict)
    }
    daily_new: list[dict] = []
    for i in range(6, -1, -1):
        d = today - dt.timedelta(days=i)
        ds = d.isoformat()
        old = prev_daily.get(ds) or {}
        if i >= 2 and isinstance(old.get("count"), int) and not old.get("stale"):
            daily_new.append({"date": ds, "count": old["count"]})
            continue
        try:
            r = subprocess.run(
                ["gh", "api",
                 f"search/issues?q=repo:{REPO}+is:pr+base:{SOURCE_BRANCH}+created:{ds}"
                 "&per_page=1"],
                capture_output=True, text=True, timeout=25)
        except subprocess.TimeoutExpired:
            r = None
        if r is not None and r.returncode == 0:
            data = json.loads(r.stdout)
            daily_new.append({"date": ds, "count": data.get("total_count", 0)})
        else:
            old = prev_daily.get(ds) or {}
            daily_new.append({"date": ds, "count": old.get("count", 0), "stale": True})

    # ── true oldest: asc query, first result ──
    oldest_pr: dict | None = None
    total_open = 0
    q_oldest = (f"search/issues?q=repo:{REPO}+is:pr+is:open+base:{SOURCE_BRANCH}"
                f"+author:{MAINTAINER}&sort=created&order=asc&per_page=1")
    try:
        r = subprocess.run(["gh", "api", q_oldest],
            capture_output=True, text=True, timeout=25)
    except subprocess.TimeoutExpired:
        r = None
    if r is not None and r.returncode == 0:
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
    while page <= 2:
        q_newest = (f"search/issues?q=repo:{REPO}+is:pr+is:open+base:{SOURCE_BRANCH}"
                 f"+author:{MAINTAINER}&sort=created&order=desc&per_page=100&page={page}")
        try:
            r2 = subprocess.run(["gh", "api", q_newest],
                capture_output=True, text=True, timeout=25)
        except subprocess.TimeoutExpired:
            break
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

    result = {
        "total_open": total_open,
        "scanned": scanned,
        "areas": dict(areas.most_common(12)),
        "oldest_pr": oldest_pr,
        "newest_pr": newest_pr,
        "daily_new": daily_new,
    }
    if not oldest_pr and total_open == 0:
        prev = _previous_state().get("backlog") or {}
        if isinstance(prev, dict) and prev.get("total_open"):
            kept = dict(prev)
            kept["daily_new"] = daily_new
            print("backlog search failed, keeping previous", file=sys.stderr)
            return kept
    return result


def release_stats() -> dict:
    """Recent releases + 30-day calendar grid (which days had releases)."""
    try:
        r = subprocess.run(
            ["gh", "release", "list", "-R", REPO, "--limit", "40",
             "--json", "tagName,name,publishedAt"],
            capture_output=True, text=True, timeout=25)
    except subprocess.TimeoutExpired:
        r = None
    if r is None or r.returncode != 0:
        prev = _previous_state().get("releases")
        if isinstance(prev, dict) and prev.get("releases"):
            print("releases failed, keeping previous", file=sys.stderr)
            return prev
        err = "" if r is None else r.stderr.strip()[:200]
        return {"releases": [], "cadence_days": None, "calendar": [], "error": err}
    rels = json.loads(r.stdout)
    now = dt.datetime.now(dt.timezone.utc)
    recent = []
    today = now.date()

    # build 30-day calendar: each day has date, weekday, and release count
    calendar: list[dict] = []
    for i in range(29, -1, -1):
        d = today - dt.timedelta(days=i)
        calendar.append({"date": d.isoformat(), "dow": d.strftime("%a")[:2],
                         "count": 0})

    for rel in rels:
        pub = parse(rel["publishedAt"])
        days_ago = (now - pub).days
        if days_ago <= 90:
            name = rel.get("name") or ""
            recent.append({"tag": rel["tagName"],
                           "version": name,
                           "date": rel["publishedAt"][:10],
                           "days_ago": days_ago})
        # mark on calendar
        pd = pub.date().isoformat()
        for c in calendar:
            if c["date"] == pd:
                c["count"] += 1

    cadence = round(90 / len(recent), 1) if recent else None
    latest = recent[0] if recent else None
    return {"releases": recent, "cadence_days": cadence, "latest": latest, "calendar": calendar}


def merge_rate() -> dict:
    """Merged PR counts in recent windows for PRs/day velocity."""
    now = dt.datetime.now(dt.timezone.utc)
    windows = [
        ("7d", now - dt.timedelta(days=7)),
        ("30d", now - dt.timedelta(days=30)),
        ("90d", now - dt.timedelta(days=90)),
    ]
    prev_rates = (_previous_state().get("merge_rate") or {})
    rates = {}
    for label, cutoff in windows:
        ds = cutoff.strftime("%Y-%m-%d")
        try:
            r = subprocess.run(
                ["gh", "api",
                 f"search/issues?q=repo:{REPO}+is:pr+is:merged+base:{SOURCE_BRANCH}+merged:>={ds}"
                 "&per_page=1"],
                capture_output=True, text=True, timeout=25)
            ok = r.returncode == 0
            payload = r.stdout if ok else ""
        except subprocess.TimeoutExpired:
            ok = False
            payload = ""
        if ok:
            data = json.loads(payload)
            total = data.get("total_count", 0)
            days = int(label[:-1])
            rates[label] = {"count": total, "per_day": round(total / days, 1)}
        else:
            old = prev_rates.get(label) if isinstance(prev_rates.get(label), dict) else {}
            days = int(label[:-1])
            total = old.get("count", 0)
            rates[label] = {"count": total, "per_day": old.get("per_day", round(total / days, 1)), "stale": True}
    rates.update(_daily_merge_extremes())
    return rates


def _daily_merge_extremes() -> dict:
    """Busiest and quietest merge days over the previous 90 UTC dates.

    Closed days are reused from the last run. Only the two newest days are
    fetched again, so a partial yesterday can still settle.
    Today is left out so a partial day does not become the low.
    """
    today = dt.datetime.now(dt.timezone.utc).date()
    days = [(today - dt.timedelta(days=offset)).isoformat() for offset in range(1, 91)]
    prev_counts = ((_previous_state().get("merge_rate") or {}).get("day_counts") or {})
    recent = set(days[:2])
    counts: dict[str, int] = {}
    need: list[str] = []
    for day in days:
        cached = prev_counts.get(day)
        if day not in recent and isinstance(cached, int):
            counts[day] = cached
        else:
            need.append(day)
    for start in range(0, len(need), 15):
        chunk = need[start:start + 15]
        fields = []
        for i, day in enumerate(chunk):
            q = f"repo:{REPO} is:pr is:merged base:{SOURCE_BRANCH} merged:{day}"
            fields.append(f'd{i}: search(query: "{q}", type: ISSUE) {{ issueCount }}')
        data = _gh_json(["api", "graphql", "-f", "query=query { " + " ".join(fields) + " }"], timeout=40)
        bucket = (data or {}).get("data") or {}
        for i, day in enumerate(chunk):
            node = bucket.get(f"d{i}") or {}
            if isinstance(node, dict) and "issueCount" in node:
                counts[day] = int(node["issueCount"])
    if len(counts) < 30:
        prev = _previous_state().get("merge_rate") or {}
        if isinstance(prev, dict) and prev.get("high_day") and prev.get("low_day"):
            print("merge-day sample failed, keeping previous", file=sys.stderr)
            return {
                "high_day": prev.get("high_day"),
                "low_day": prev.get("low_day"),
                "days_sampled": prev.get("days_sampled") or 0,
                "day_counts": prev_counts if isinstance(prev_counts, dict) else {},
            }
        return {}
    peak = max(counts.values())
    floor = min(counts.values())
    high_day = max(day for day, count in counts.items() if count == peak)
    low_day = max(day for day, count in counts.items() if count == floor)
    return {
        "high_day": {"date": high_day, "count": peak},
        "low_day": {"date": low_day, "count": floor},
        "days_sampled": len(counts),
        "day_counts": counts,
    }


def _ago_from(ts: str, now: dt.datetime) -> tuple[str, int]:
    """Return a short age label and whole days since ``ts``."""
    created = parse(ts)
    delta = now - created
    days = max(0, delta.days)
    seconds = max(0, int(delta.total_seconds()))
    if seconds < 3600:
        return f"{seconds // 60}m ago", 0
    if days < 1:
        return f"{seconds // 3600}h ago", 0
    return f"{days}d ago", days


def _previous_section(name: str, empty: dict) -> dict:
    prev = _previous_state().get(name)
    useful = isinstance(prev, dict) and (
        prev.get("recent") or prev.get("contributors") or prev.get("total_open")
    )
    if useful:
        print(f"{name} failed, keeping previous", file=sys.stderr)
        return prev
    return empty


def _previous_state() -> dict:
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _atomic_write(path: pathlib.Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _gh_json(args: list[str], timeout: int = 25):
    try:
        r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"gh timed out: {' '.join(args)[:80]}", file=sys.stderr)
        return None
    if r.returncode != 0:
        print(f"gh {' '.join(args)[:80]} failed: {r.stderr.strip()[:180]}", file=sys.stderr)
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


def issues_stats() -> dict:
    """Open-issue working set for the issues tab (newest updates, up to 100)."""
    now = dt.datetime.now(dt.timezone.utc)
    total_open = 0
    total_closed = 0
    got_open = False
    got_closed = False

    for state in ("open", "closed"):
        data = _gh_json(["api", f"search/issues?q=repo:{REPO}+type:issue+state:{state}&per_page=1"])
        if isinstance(data, dict):
            if state == "open":
                total_open = data.get("total_count", 0)
                got_open = True
            else:
                total_closed = data.get("total_count", 0)
                got_closed = True

    data = _gh_json([
        "api",
        f"search/issues?q=repo:{REPO}+type:issue+state:open&sort=updated&order=desc&per_page=100",
    ])
    recent = []
    if isinstance(data, dict):
        for item in data.get("items", []):
            labels = [l.get("name", "") for l in item.get("labels", []) if l.get("name")]
            display = [name for name in labels
                       if not name.startswith(("type/", "comp/", "area/", "sweeper:", "P"))]
            ago, age_days = _ago_from(item["created_at"], now)
            assignee = (item.get("assignee") or {}).get("login") or ""
            recent.append({
                "number": item["number"],
                "title": " ".join((item.get("title") or "").split()),
                "labels": display[:3],
                "all_labels": labels,
                "author": (item.get("user") or {}).get("login", ""),
                "assignee": assignee,
                "unassigned": not assignee,
                "created_at": item["created_at"],
                "updated_at": item.get("updated_at") or item["created_at"],
                "ago": ago,
                "age_days": age_days,
                "comments": item.get("comments", 0) or 0,
                "url": item.get("html_url") or f"https://github.com/{REPO}/issues/{item['number']}",
            })

    result = {
        "total_open": total_open,
        "total_closed": total_closed,
        "scanned": len(recent),
        "recent": recent,
    }
    if not recent:
        kept = _previous_section("issues", result)
        if isinstance(kept, dict) and kept.get("recent"):
            kept = dict(kept)
            if total_open or got_open:
                kept["total_open"] = total_open
            if total_closed or got_closed:
                kept["total_closed"] = total_closed
            return kept
    return result


def _review_counts() -> dict[str, int]:
    """Reviews on the 40 most recently updated pull requests."""
    query = """
    query($q: String!) {
      search(query: $q, type: ISSUE, first: 40) {
        nodes {
          ... on PullRequest {
            reviews(first: 20) { nodes { state author { login } } }
          }
        }
      }
    }
    """
    data = _gh_json([
        "api", "graphql",
        "-f", f"query={query}",
        "-f", f"q=repo:{REPO} is:pr",
    ], timeout=30)
    counts: dict[str, int] = {}
    nodes = (((data or {}).get("data") or {}).get("search") or {}).get("nodes") or []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        for review in ((node.get("reviews") or {}).get("nodes") or []):
            if not isinstance(review, dict):
                continue
            if review.get("state") not in ("APPROVED", "CHANGES_REQUESTED", "COMMENTED"):
                continue
            login = ((review.get("author") or {}).get("login")) or ""
            if login:
                counts[login] = counts.get(login, 0) + 1
    return counts


def contributors_stats() -> dict:
    """Top contributors with this-week commits, recent reviews, and a new flag."""
    now_ts = int(dt.datetime.now(dt.timezone.utc).timestamp())
    reviews = _review_counts()
    data = _gh_json(["api", f"repos/{REPO}/stats/contributors"], timeout=40)
    if not isinstance(data, list):
        # Stats are computed asynchronously; one retry covers the usual 202.
        import time
        time.sleep(2)
        data = _gh_json(["api", f"repos/{REPO}/stats/contributors"], timeout=40)

    contribs: list[dict] = []
    if isinstance(data, list):
        for row in data:
            author = row.get("author") or {}
            login = author.get("login") or ""
            if not login:
                continue
            weeks = row.get("weeks") or []
            active = [w for w in weeks if (w.get("c") or 0) > 0]
            latest = max(weeks, key=lambda w: w.get("w") or 0) if weeks else {}
            first = min((w.get("w") or 0) for w in active) if active else 0
            contribs.append({
                "login": login,
                "contributions": row.get("total") or 0,
                "week_commits": latest.get("c") or 0,
                "reviews": reviews.get(login, 0),
                "new": bool(first and (now_ts - first) < 28 * 86400),
                "avatar_url": author.get("avatar_url") or "",
                "html_url": author.get("html_url") or f"https://github.com/{login}",
            })
    if not contribs:
        fallback = _gh_json(["api", f"repos/{REPO}/contributors?per_page=40"])
        if isinstance(fallback, list):
            for c in fallback:
                login = c.get("login") or ""
                if not login:
                    continue
                contribs.append({
                    "login": login,
                    "contributions": c.get("contributions") or 0,
                    "week_commits": 0,
                    "reviews": reviews.get(login, 0),
                    "new": False,
                    "avatar_url": c.get("avatar_url") or "",
                    "html_url": c.get("html_url") or f"https://github.com/{login}",
                })

    contribs.sort(key=lambda x: x.get("contributions", 0), reverse=True)
    result = {"contributors": contribs[:40]}
    if contribs:
        return result
    return _previous_section("contributors", result)


def merge_velocity() -> dict:
    """Per-area merge velocity from last ~40 merges (hours)."""
    import re
    from collections import defaultdict

    try:
        r = subprocess.run(
            ["gh", "pr", "list", "-R", REPO, "--state", "merged", "--base",
             SOURCE_BRANCH, "--limit", "40", "--json",
             "title,mergedAt,createdAt"],
            capture_output=True, text=True, timeout=25)
    except subprocess.TimeoutExpired:
        r = None
    if r is None or r.returncode != 0:
        prev = _previous_state().get("merge_velocity")
        if isinstance(prev, dict) and prev:
            print("merge velocity failed, keeping previous", file=sys.stderr)
            return prev
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


def _ci_summary(rollup) -> dict:
    ok = fail = pending = total = 0
    for check in rollup or []:
        if not isinstance(check, dict):
            continue
        total += 1
        conclusion = str(check.get("conclusion") or check.get("state") or "").upper()
        status = str(check.get("status") or "").upper()
        if conclusion in ("SUCCESS", "NEUTRAL", "SKIPPED") or status == "SUCCESS":
            ok += 1
        elif conclusion in ("FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "ERROR", "STARTUP_FAILURE") or status in ("FAILURE", "ERROR"):
            fail += 1
        else:
            pending += 1
    if total == 0:
        label = "none"
    elif fail:
        label = "failing"
    elif pending:
        label = "pending"
    else:
        label = "passing"
    return {"ci": label, "ci_ok": ok, "ci_total": total}


def _queue_for(item: dict) -> str:
    if item.get("draft"):
        return "draft"
    review = item.get("review") or ""
    if review == "APPROVED":
        return "approved"
    if review == "CHANGES_REQUESTED":
        return "changes"
    return "needs-review"


def prs_stats() -> dict:
    """Recently updated open PRs, with review decision and CI, for the PR tab."""
    now = dt.datetime.now(dt.timezone.utc)
    total_open = 0
    total_closed = 0
    got_open = False
    got_closed = False
    for state in ("open", "closed"):
        data = _gh_json(["api", f"search/issues?q=repo:{REPO}+type:pr+state:{state}&per_page=1"])
        if isinstance(data, dict):
            if state == "open":
                total_open = data.get("total_count", 0)
                got_open = True
            else:
                total_closed = data.get("total_count", 0)
                got_closed = True

    # `gh pr list` carries review and CI fields the search index does not.
    listed = _gh_json([
        "pr", "list", "-R", REPO, "--state", "open", "--limit", "50",
        "--json",
        "number,title,author,updatedAt,isDraft,reviewDecision,additions,deletions,url,statusCheckRollup,labels",
    ], timeout=40)
    recent = []
    if isinstance(listed, list):
        for item in listed:
            ago, _days = _ago_from(item["updatedAt"], now)
            labels = [l.get("name", "") for l in item.get("labels") or [] if isinstance(l, dict) and l.get("name")]
            row = {
                "number": item["number"],
                "title": " ".join((item.get("title") or "").split()),
                "author": (item.get("author") or {}).get("login", ""),
                "draft": bool(item.get("isDraft")),
                "review": item.get("reviewDecision") or "",
                "additions": item.get("additions") or 0,
                "deletions": item.get("deletions") or 0,
                "labels": labels,
                "updated_at": item["updatedAt"],
                "ago": ago,
                "url": item.get("url") or f"https://github.com/{REPO}/pull/{item['number']}",
            }
            row.update(_ci_summary(item.get("statusCheckRollup")))
            row["queue"] = _queue_for(row)
            recent.append(row)

    result = {
        "total_open": total_open,
        "total_closed": total_closed,
        "scanned": len(recent),
        "recent": recent,
    }
    if not recent:
        kept = _previous_section("pull_requests", result)
        if isinstance(kept, dict) and kept.get("recent"):
            kept = dict(kept)
            if total_open or got_open:
                kept["total_open"] = total_open
            if total_closed or got_closed:
                kept["total_closed"] = total_closed
            return kept
    # Search totals can fail independently of `gh pr list`; a 0 from a failed
    # search query must never zero the header over a live list of PRs.
    if recent and not got_open:
        prev = _previous_state().get("pull_requests") or {}
        if isinstance(prev, dict) and prev.get("total_open"):
            result["total_open"] = prev.get("total_open")
    if recent and not got_closed:
        prev = _previous_state().get("pull_requests") or {}
        if isinstance(prev, dict) and prev.get("total_closed"):
            result["total_closed"] = prev.get("total_closed")
    return result


def ecosystem_index(releases: dict) -> list[dict]:
    """Repos, issues, pull requests, discussions, and releases across Hermes."""
    docs: list[dict] = []
    failed: set[str] = set()
    repos = _gh_json([
        "api",
        "search/repositories?q=hermes+org:NousResearch&sort=updated&per_page=30",
    ])
    if not isinstance(repos, dict):
        failed.add("repo")
    else:
        for repo in repos.get("items") or []:
            full = repo.get("full_name") or ""
            docs.append({
                "kind": "repo",
                "title": full,
                "text": repo.get("description") or "",
                "repo": full,
                "url": repo.get("html_url") or "",
                "author": (repo.get("owner") or {}).get("login") or "",
                "updated_at": repo.get("updated_at") or "",
            })

    for kind, qual in (("issue", "is:issue"), ("pr", "is:pr")):
        found = _gh_json([
            "api",
            f"search/issues?q=org:NousResearch+hermes+{qual}&sort=updated&order=desc&per_page=40",
        ])
        if not isinstance(found, dict):
            failed.add(kind)
            continue
        for item in found.get("items") or []:
            # repository_url is .../repos/OWNER/NAME
            parts = (item.get("repository_url") or "").rstrip("/").split("/")
            full = "/".join(parts[-2:]) if len(parts) >= 2 else ""
            docs.append({
                "kind": kind,
                "title": " ".join((item.get("title") or "").split()),
                "text": "",
                "number": item.get("number"),
                "repo": full,
                "author": (item.get("user") or {}).get("login") or "",
                "state": item.get("state") or "",
                "labels": [l.get("name", "") for l in item.get("labels") or [] if isinstance(l, dict)],
                "comments": item.get("comments") or 0,
                "url": item.get("html_url") or "",
                "updated_at": item.get("updated_at") or "",
            })

    discussions = _gh_json([
        "api", "graphql",
        "-f", "query=query { search(query: \"org:NousResearch hermes\", type: DISCUSSION, first: 20) { nodes { ... on Discussion { title url updatedAt author { login } repository { nameWithOwner } } } } }",
    ], timeout=30)
    nodes = (((discussions or {}).get("data") or {}).get("search") or {}).get("nodes") or []
    for node in nodes:
        if not isinstance(node, dict) or not node.get("title"):
            continue
        docs.append({
            "kind": "discussion",
            "title": node.get("title") or "",
            "text": "",
            "repo": (node.get("repository") or {}).get("nameWithOwner") or "",
            "author": (node.get("author") or {}).get("login") or "",
            "url": node.get("url") or "",
            "updated_at": node.get("updatedAt") or "",
        })

    for rel in (releases or {}).get("releases") or []:
        tag = rel.get("tag") or ""
        docs.append({
            "kind": "release",
            "title": tag,
            "text": rel.get("version") or "",
            "repo": REPO,
            "url": f"https://github.com/{REPO}/releases/tag/{tag}",
            "updated_at": rel.get("date") or "",
            "author": "",
        })
    if failed:
        prev = _previous_state().get("ecosystem")
        if isinstance(prev, list) and prev:
            docs.extend(
                row for row in prev
                if isinstance(row, dict) and row.get("kind") in failed
            )
            print(f"ecosystem search failed for {', '.join(sorted(failed))}; keeping previous rows",
                  file=sys.stderr)
    return docs


# ── main ────────────────────────────────────────────────────────────────────


def _fresh_row(kind: str, item: dict, now: dt.datetime) -> dict | None:
    created = item.get("created_at") or ""
    try:
        when = parse(created)
    except (TypeError, ValueError):
        return None
    ago, _days = _ago_from(created, now)
    return {
        "kind": kind,
        "number": item.get("number"),
        "title": " ".join((item.get("title") or "").split()),
        "author": (item.get("user") or {}).get("login") or item.get("author") or "",
        "url": item.get("html_url") or item.get("url") or "",
        "created_at": created,
        "ago": ago,
        "comments": item.get("comments") or 0,
        "lane": "merged" if (
            ((item.get("pull_request") or {}).get("merged_at")) or item.get("lane") == "merged"
        ) else kind,
        "_when": when,
    }


def fresh_wire(now: dt.datetime) -> list[dict]:
    """PRs and issues opened in the last 48 hours.

    Keeps the previous in-window rows, refreshes the last 3 hours, and backfills
    one 6-hour slice older than what we already have. A single search cannot
    return a full busy 48 hours.
    """
    cutoff = now - dt.timedelta(hours=48)
    items: list[dict] = []
    oldest_by: dict[str, dt.datetime] = {}
    for row in _previous_state().get("fresh") or []:
        if not isinstance(row, dict):
            continue
        kind_name = "issue" if row.get("kind") == "issue" else "pr"
        kept = _fresh_row(kind_name, row, now)
        if kept is None:
            continue
        when = kept.pop("_when")
        if when < cutoff:
            continue
        items.append(kept)
        if kind_name not in oldest_by or when < oldest_by[kind_name]:
            oldest_by[kind_name] = when

    def pull(kind: str, qual: str, created: str, pages: int) -> bool:
        ok = False
        for page in range(1, pages + 1):
            data = _gh_json([
                "api",
                (
                    f"search/issues?q=repo:{REPO}+{qual}+{created}"
                    f"&sort=created&order=desc&per_page=100&page={page}"
                ),
            ])
            if not isinstance(data, dict):
                break
            ok = True
            batch = data.get("items") or []
            if not batch:
                break
            older = False
            for item in batch:
                row = _fresh_row(kind, item, now)
                if row is None:
                    continue
                if row.pop("_when") < cutoff:
                    older = True
                    continue
                items.append(row)
            if older or len(batch) < 100:
                break
        return ok

    for kind, qual in (("pr", "is:pr"), ("issue", "is:issue")):
        recent = (now - dt.timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
        if not pull(kind, qual, f"created:>={recent}", 2):
            print(f"fresh recent search failed for {kind}; keeping previous rows", file=sys.stderr)
        oldest = oldest_by.get(kind)
        if oldest is None or oldest - cutoff > dt.timedelta(minutes=30):
            end = oldest or now
            begin = max(cutoff, end - dt.timedelta(hours=6))
            window = (
                begin.strftime("%Y-%m-%dT%H:%M:%SZ")
                + ".."
                + end.strftime("%Y-%m-%dT%H:%M:%SZ")
            )
            if not pull(kind, qual, f"created:{window}", 3):
                print(f"fresh backfill failed for {kind}", file=sys.stderr)
    deduped: dict[tuple, dict] = {}
    for row in items:
        deduped[(row.get("kind"), row.get("number"))] = row
    fresh = list(deduped.values())
    fresh.sort(key=lambda row: row.get("created_at") or "", reverse=True)
    return fresh


# ── quality program (local lane state; filesystem reads only) ───────────────
# Bridges the nous-pr-bot maintainer program into this dashboard. Read-only,
# never touches GitHub, never posts anything.

NOUS_HOME = pathlib.Path.home() / ".hermes" / "profiles" / "nous-pr-bot" / "scripts"
NOUS_CORPUS = (pathlib.Path.home() / "Nous-Fleet" / "reviews" / "continuous"
               / "hermes-quality-program" / "corpus-trends.md")
NOUS_MERGE_STATE = NOUS_HOME / "merge_state"
ECO_FILE = ROOT / "merge_state" / "ecosystem" / "ecosystem.json"


def ecosystem_catalog() -> dict:
    """Plugin catalog + optional skills from the local ingest cache.

    Populated by ecosystem_ingest.py (daily, ~500 raw fetches). Missing or
    stale file yields empty lists — the site renders an empty section, not
    a failed build.
    """
    out = {"generated": "", "plugins": [], "skills": []}
    try:
        data = json.loads(ECO_FILE.read_text(encoding="utf-8"))
    except Exception:
        return out
    plugins = data.get("plugins")
    if isinstance(plugins, list):
        out["plugins"] = [p for p in plugins if isinstance(p, dict)]
    skills = data.get("skills")
    if isinstance(skills, list):
        out["skills"] = [s for s in skills if isinstance(s, dict)]
    out["generated"] = data.get("generated") or ""
    return out


def _read_json(path: pathlib.Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def _corpus_stats() -> dict:
    """Newest corpus totals and leading bug_class from the trends journal.

    The journal is reverse-chronological, so the FIRST match of each
    marker is the newest run and the trailing blocks are history.
    """
    out = {
        "total": 0,
        "batch": 0,
        "top_bug_class": "",
        "ratio": "",
        "regression_pct": "",
    }
    try:
        text = NOUS_CORPUS.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return out

    totals = re.findall(r"\*\*Total entries:\*\*\s*(\d+)", text)
    if totals:
        out["total"] = int(totals[0])

    # newest bug_class table: rank 1 wins
    blocks = text.split("### Top 5 bug_class")
    if len(blocks) > 1:
        rows = re.findall(r"\|\s*1\s*\|\s*([A-Za-z0-9 _-]+?)\s*\|", blocks[1])
        if rows:
            out["top_bug_class"] = rows[0].strip()

    # newest test-discipline block
    tb = text.split("### test_discipline ratio")
    if len(tb) > 1:
        newest = tb[1]
        batch = re.search(r"Of\s+(\d+)\s+new entries", newest)
        if batch:
            out["batch"] = int(batch.group(1))
        ratios = re.findall(r"\*\*(\d+(?:\s*/\s*\d+)+)\*\*", newest)
        if ratios:
            out["ratio"] = ratios[0].strip()
        pct = re.search(r"`regression-test`[^\n]*?≈\s*(\d+)\s*%", newest)
        if pct:
            out["regression_pct"] = pct.group(1) + "%"
    return out


def _corpus_live() -> dict:
    """Live corpus size and curator marker from the merge_state store.

    merge_corpus.md is the append-only synthesis corpus; each entry is a
    level-2 heading. last_curated_count is the curator's last published
    run, which is what corpus-trends.md documents.
    """
    out = {"live_total": 0, "curated_total": 0}
    try:
        text = (NOUS_MERGE_STATE / "merge_corpus.md").read_text(
            encoding="utf-8", errors="replace")
        out["live_total"] = len(re.findall(r"^## ", text, re.M))
    except Exception:
        pass
    try:
        raw = (NOUS_MERGE_STATE / "last_curated_count").read_text(encoding="utf-8")
        digits = re.search(r"\d+", raw)
        if digits:
            out["curated_total"] = int(digits.group(0))
    except Exception:
        pass
    return out


def quality_program(lane_open: int | None = None) -> dict:
    """Maintainer-program state merged into the dashboard.

    Sources are local files owned by the nous-pr-bot profile: the watch
    ledger, the review queue, the SWE-2 review drafts, and the corpus
    trends journal. Every read is defensive; a missing file yields an
    empty section rather than a failed build.
    """
    now = dt.datetime.now(dt.timezone.utc)
    state = _read_json(NOUS_HOME / "nous_pr_state.json", {}) or {}
    tracked = state.get("tracked")
    if not isinstance(tracked, dict):
        tracked = {}

    ledger: list[dict] = []
    try:
        for line in (NOUS_HOME / "nous_pr_removed.jsonl").read_text(
                encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ledger.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        pass

    queue = _read_json(NOUS_HOME / "review_queue.json", {}) or {}

    drafts: list[dict] = []
    try:
        for path in sorted((NOUS_HOME / "review_drafts").glob("*.md")):
            head = path.read_text(encoding="utf-8", errors="replace")[:600]
            verdict = score = ""
            for line in head.splitlines()[:16]:
                if line.startswith("**Verdict:**"):
                    verdict = line.split(":", 1)[-1].strip().strip("*").strip()
                elif line.startswith("**Score:**"):
                    score = line.split(":", 1)[-1].strip().strip("*").strip()
            drafts.append({"pr": str(path.stem), "verdict": verdict, "score": score})
    except Exception:
        pass

    posted = 0
    try:
        posted = sum(1 for line in (NOUS_HOME / "review_posted.jsonl")
                     .read_text(encoding="utf-8").splitlines() if line.strip())
    except Exception:
        pass

    followups = []
    for item in (queue.get("followups") or []):
        if isinstance(item, dict):
            followups.append({
                "pr": item.get("pr"),
                "gap": " ".join(str(item.get("gap") or "").split())[:240],
                "since": item.get("since") or "",
            })

    corpus = _corpus_stats()
    live = _corpus_live()

    last_removed = {}
    if ledger:
        row = ledger[-1]
        last_removed = {
            "pr": row.get("pr"),
            "reason": row.get("reason") or "",
            "title": " ".join(str(row.get("title") or "").split())[:110],
            "ts": row.get("ts") or "",
        }

    ready_list = queue.get("ready")
    pending_list = queue.get("pending")
    stale_list = queue.get("stale_drafts")
    if not isinstance(ready_list, list):
        ready_list = []
    if not isinstance(pending_list, list):
        pending_list = []
    if not isinstance(stale_list, list):
        stale_list = []

    counts = {
        "watch_tracked": len(tracked),
        "watch_definition": "open PRs from the whole maintainer team",
        "lane_open": lane_open,
        "lane_definition": f"PRs authored by or involving {MAINTAINER}",
    }

    return {
        "generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tracked_open": len(tracked),
        "removed_total": len(ledger),
        "last_removed": last_removed,
        "corpus": {
            "live_total": live.get("live_total") or 0,
            "curated_total": live.get("curated_total") or corpus.get("total") or 0,
            "batch": corpus.get("batch") or 0,
            "top_bug_class": corpus.get("top_bug_class") or "n/a",
            "ratio": corpus.get("ratio") or "n/a",
            "regression_pct": corpus.get("regression_pct") or "n/a",
        },
        "review_queue": {
            "ready": len(ready_list),
            "pending": len(pending_list),
            "stale_drafts": len(stale_list),
            "followups": len(followups),
        },
        "drafts": drafts,
        "drafts_count": len(drafts),
        "posted_reviews": posted,
        "followups": followups,
        "counts": counts,
    }


def _safe(name: str, fn):
    try:
        return fn()
    except Exception as exc:
        print(f"{name} failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return None


def main() -> int:
    now = dt.datetime.now(dt.timezone.utc)
    prev = _previous_state()
    from concurrent.futures import ThreadPoolExecutor, wait
    pool = ThreadPoolExecutor(max_workers=4)
    jobs = {
        "open": pool.submit(_safe, "open", open_prs),
        "merged": pool.submit(_safe, "merged", lambda: gh([
            "pr", "list", "-R", REPO, "--state", "merged", "--limit", "40",
            "--base", SOURCE_BRANCH, "--search", "sort:updated-desc",
            "--json", MERGED_FIELDS,
        ])),
        "fresh": pool.submit(_safe, "fresh", lambda: fresh_wire(now)),
        "backlog": pool.submit(_safe, "backlog", backlog_stats),
        "releases": pool.submit(_safe, "releases", release_stats),
        "merge_velocity": pool.submit(_safe, "merge_velocity", merge_velocity),
        "merge_rate": pool.submit(_safe, "merge_rate", merge_rate),
        "issues": pool.submit(_safe, "issues", issues_stats),
        "pull_requests": pool.submit(_safe, "pull_requests", prs_stats),
        "contributors": pool.submit(_safe, "contributors", contributors_stats),
        "ecosystem": pool.submit(
            _safe, "ecosystem", lambda: ecosystem_index(prev.get("releases") or {})
        ),
    }
    _done, pending_jobs = wait(list(jobs.values()), timeout=180)
    got = {}
    for name, job in jobs.items():
        if job in _done:
            got[name] = job.result()
        else:
            print(f"{name} still running after 180s, keeping previous", file=sys.stderr)
            got[name] = None
    pool.shutdown(wait=False, cancel_futures=True)

    raw_open = got["open"]
    if not isinstance(raw_open, list):
        print("open pr list failed, keeping previous pending", file=sys.stderr)
        pending = prev.get("pending") if isinstance(prev.get("pending"), list) else []
        pend_count = prev.get("open_in_maintainer_lane") or len(pending)
    else:
        pend_all = [norm_pending(p, now) for p in raw_open]
        pending = sorted(pend_all, key=lambda p: (-p["score"], p["age_min"]))[:N_PENDING]
        pend_count = len(pend_all)

    raw_merged = got["merged"]
    if not isinstance(raw_merged, list):
        print("merged pr list failed, keeping previous merged", file=sys.stderr)
        merged = prev.get("merged") if isinstance(prev.get("merged"), list) else []
        merged_scanned = prev.get("merged_scanned") or len(merged)
    else:
        merged_all = [p for p in raw_merged if isinstance(p, dict) and p.get("mergedAt")]
        merged_all.sort(key=lambda p: p["mergedAt"], reverse=True)
        merged_lane = [p for p in merged_all
                       if (p.get("mergedBy") or {}).get("login") == MAINTAINER
                       or (p.get("author") or {}).get("login") == MAINTAINER]
        merged = [norm_merged(p, now) for p in merged_lane[:N_MERGED]]
        merged_scanned = len(merged_all)
    seen_merged = set()
    combined = []
    for row in list(merged) + [row for row in (prev.get("merged") or []) if isinstance(row, dict)]:
        number = row.get("number")
        if number in seen_merged:
            continue
        seen_merged.add(number)
        combined.append(row)

    def with_fresh_age(row: dict) -> dict:
        stamp = row.get("merged_at") or ""
        if not stamp:
            return row
        try:
            minutes, label = age(stamp, now)
        except (TypeError, ValueError):
            return row
        fresh_row = dict(row)
        fresh_row["age_min"] = minutes
        fresh_row["ago"] = label
        return fresh_row

    merged = sorted(
        (with_fresh_age(row) for row in combined),
        key=lambda row: row.get("merged_at") or "",
        reverse=True,
    )[:N_MERGED]
    merged_numbers = {row.get("number") for row in merged}
    pending = [row for row in pending if row.get("number") not in merged_numbers]

    def section(name: str):
        value = got[name]
        if value is None:
            print(f"{name} failed, keeping previous", file=sys.stderr)
            return prev.get(name)
        return value

    fresh = got["fresh"] if isinstance(got["fresh"], list) else (prev.get("fresh") or [])
    releases = section("releases") or {}
    quality = quality_program(lane_open=pend_count)
    eco = ecosystem_catalog()
    state = {
        "generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo": REPO,
        "branch": SOURCE_BRANCH,
        "maintainer": MAINTAINER,
        "open_in_maintainer_lane": pend_count,
        "merged_scanned": merged_scanned,
        "quality": quality,
        "catalog": eco,
        "pending": pending,
        "merged": merged,
        "backlog": section("backlog") or {},
        "releases": releases,
        "merge_velocity": section("merge_velocity") or {},
        "merge_rate": section("merge_rate") or {},
        "issues": section("issues") or {},
        "pull_requests": section("pull_requests") or {},
        "contributors": section("contributors") or {},
        "ecosystem": got["ecosystem"] if isinstance(got["ecosystem"], list) else (prev.get("ecosystem") or []),
        "fresh": fresh,
    }
    _atomic_write(OUT, json.dumps(state, indent=2) + "\n")
    print(f"wrote {OUT.name}: {len(pending)} pending / {len(merged)} merged "
          f"(maintainer lane: {pend_count} open; {merged_scanned} merges "
          f"scanned) at {state['generated']}")
    for p in pending:
        print(f"  GREEN #{p['number']:<7} score={p['score']:<3} {p['label']:<20} "
              f"{p['ago']:<7} {p['title'][:46]}")
    for m in merged:
        print(f"  BLUE  #{m['number']:<7} {m['ago']:<7} by {m['author'][:14]:<14} "
              f"{m['title'][:44]}")
    bl = state.get("backlog") if isinstance(state.get("backlog"), dict) else {}
    oldest = bl.get("oldest_pr") or {}
    q = state.get("quality")
    if isinstance(q, dict):
        rq = q.get("review_queue")
        if not isinstance(rq, dict):
            rq = {}
        cp = q.get("corpus")
        if not isinstance(cp, dict):
            cp = {}
        print(f"  QUALITY watch={q.get('tracked_open', 0)} open · "
              f"removed={q.get('removed_total', 0)} · "
              f"corpus live={cp.get('live_total', 0)}/curated={cp.get('curated_total', 0)} · "
              f"drafts={q.get('drafts_count', 0)} · posted={q.get('posted_reviews', 0)} · "
              f"queue r/p/s/f={rq.get('ready', 0)}/{rq.get('pending', 0)}/"
              f"{rq.get('stale_drafts', 0)}/{rq.get('followups', 0)}")
    if oldest.get("number"):
        print(f"  BACKLOG {bl.get('total_open', 0)} open · oldest #{oldest['number']} "
              f"({oldest.get('age_days', '?')}d) · areas={dict(list(bl.get('areas', {}).items())[:6])}")
    else:
        print(f"  BACKLOG {bl.get('total_open', 0)} open · oldest n/a · "
              f"areas={dict(list((bl.get('areas') or {}).items())[:6])}")
    rl = state["releases"] if isinstance(state.get("releases"), dict) else {}
    rels = rl.get("releases") or []
    print(f"  RELEASES {len(rels)} in 90d · cadence ~{rl.get('cadence_days')}d"
          if rl.get("cadence_days") else "  RELEASES N/A")
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())