#!/usr/bin/env python3
"""Regenerate the Nous.Space data blocks in index.html from live GitHub data.

Layout contract (do not change without asking Jefferson):
  Cubes   (left zone)  : the 4 merges just BEFORE the newest 4 — oldest far left,
                         newest sits against the amber divider.
                         Fields: PR number / +add -del / N commits · M files / ~N min
  Details (right zone) : the 4 MOST RECENT merges into main, newest first.
                         Fields: PR number / title / +add -del · M files

`~N min` is the AGE of the merge at generation time, not the open->merge duration.

Usage:  python3 refresh_data.py [--dry-run]
Requires: gh CLI, authenticated, and network access to GitHub.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import subprocess
import sys

REPO = "NousResearch/hermes-agent"
SOURCE_BRANCH = "main"
N_CUBES = 4
N_DETAILS = 4
TITLE_MAX = 70

ROOT = pathlib.Path(__file__).resolve().parent
INDEX = ROOT / "index.html"

CUBE_RE = re.compile(r'(<div class="zone-left" id="zoneLeft">)(.*?)(\n  </div>)', re.S)
DETAIL_RE = re.compile(r'(<div class="zone-right">)(.*?)(\n  </div>)', re.S)


def merged_prs(limit: int = 40) -> list[dict]:
    """Merged PRs into SOURCE_BRANCH, newest merge first."""
    out = subprocess.run(
        ["gh", "pr", "list", "-R", REPO, "--state", "merged", "--limit", str(limit),
         "--base", SOURCE_BRANCH,
         "--json", "number,title,mergedAt,createdAt,additions,deletions,changedFiles,commits"],
        capture_output=True, text=True, check=True,
    ).stdout
    prs = [p for p in json.loads(out) if p.get("mergedAt")]
    prs.sort(key=lambda p: p["mergedAt"], reverse=True)
    return prs


def parse(ts: str) -> dt.datetime:
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def age_min(m: dt.datetime, now: dt.datetime) -> int:
    return int(round((now - m).total_seconds() / 60))


def clip(title: str, limit: int = TITLE_MAX) -> str:
    title = " ".join(title.split())
    return title if len(title) <= limit else title[: limit - 1].rstrip() + "\u2026"


def cube_html(pr: dict, now: dt.datetime) -> str:
    commits = len(pr["commits"])
    files = pr["changedFiles"]
    return f"""    <div class="cube">
      <div class="cube-face">
        <div class="cube-pr">#{pr['number']}</div>
        <div class="cube-diff"><span class="add">+{pr['additions']}</span>&nbsp;<span class="del">-{pr['deletions']}</span></div>
        <div class="cube-prs">{plural(commits, 'commit')} · {plural(files, 'file')}</div>
        <div class="cube-time">~{age_min(parse(pr['mergedAt']), now)} min</div>
      </div>
    </div>"""


def detail_html(pr: dict) -> str:
    return f"""    <div class="detail-box">
      <div class="d-pr">#{pr['number']}</div>
      <div class="d-title">{clip(pr['title'])}</div>
      <div class="d-diff"><span class="add">+{pr['additions']}</span>&nbsp;<span class="del">-{pr['deletions']}</span> · {plural(pr['changedFiles'], 'file')}</div>
    </div>"""


def main() -> int:
    dry = "--dry-run" in sys.argv
    html = INDEX.read_text(encoding="utf-8")

    if not CUBE_RE.search(html) or not DETAIL_RE.search(html):
        print("ERROR: could not find the zone-left / zone-right blocks in index.html", file=sys.stderr)
        return 2

    now = dt.datetime.now(dt.UTC)
    prs = merged_prs()
    need = N_CUBES + N_DETAILS
    if len(prs) < need:
        print(f"ERROR: only {len(prs)} merged PRs found, need {need}", file=sys.stderr)
        return 3

    details = prs[:N_DETAILS]                      # newest first
    cubes_src = prs[N_DETAILS:N_DETAILS + N_CUBES]  # next 4
    cubes = list(reversed(cubes_src))               # oldest far left -> newest at divider

    cubes_block = "\n" + "\n".join(cube_html(p, now) for p in cubes)
    details_block = "\n" + "\n".join(detail_html(p) for p in details)

    html = CUBE_RE.sub(lambda m: m.group(1) + cubes_block + m.group(3), html, count=1)
    html = DETAIL_RE.sub(lambda m: m.group(1) + details_block + m.group(3), html, count=1)

    if dry:
        print("cubes  :", ", ".join(f"#{p['number']}" for p in cubes))
        print("details:", ", ".join(f"#{p['number']}" for p in details))
        print("age(now):", now.strftime("%Y-%m-%d %H:%M:%SZ"))
        return 0

    INDEX.write_text(html, encoding="utf-8")
    print(f"index.html updated at {now.strftime('%Y-%m-%d %H:%M:%SZ')}")
    print("cubes  :", ", ".join(f"#{p['number']} (~{age_min(parse(p['mergedAt']), now)}m)" for p in cubes))
    print("details:", ", ".join(f"#{p['number']}" for p in details))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
