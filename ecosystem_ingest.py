#!/usr/bin/env python3
"""Ingest the Hermes ecosystem catalog into nous-space state.

Sources (upstream hermes-agent repo, public data):
  - plugin-catalog/*.yaml    338 curated plugin entries (name, repo, SHA pin,
                             description, maintainer, tier, category, docs_url,
                             capabilities)
  - optional-skills/**/SKILL.md frontmatter  152 skills across 24 categories

Output: ~/nous-space/merge_state/ecosystem/{plugins.json,skills.json}
Read by fetch_state.py at refresh time. Local-only; no deploy.

Fetch strategy: one `gh api git/trees/main?recursive=1` call lists every path
(1 credit), then one raw fetch per file. ~500 files once daily — well inside
the shared 600 req/h budget. Cache-on-disk with mtime check; refresh interval
24h (catalogs change only via merged PRs).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
import time

REPO = "NousResearch/hermes-agent"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "merge_state", "ecosystem")
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/main"
REFRESH_SECONDS = 24 * 3600


def gh_json(args, timeout=60):
    proc = subprocess.run(["gh", "api"] + args, capture_output=True,
                          text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"gh api failed: {proc.stderr[:200]}")
    return json.loads(proc.stdout)


def raw_fetch(path: str, timeout=30) -> str | None:
    import urllib.request
    url = f"{RAW_BASE}/{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def parse_simple_yaml(text: str) -> dict:
    """Minimal YAML reader for the flat plugin-catalog shape.

    Fields are scalars or single-level lists under `capabilities:`. Good
    enough for this catalog; avoids a PyYAML dependency.
    """
    out: dict = {}
    current_list_key = None
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if indent == 0:
            current_list_key = None
            if ":" in stripped:
                key, _, val = stripped.partition(":")
                val = val.strip()
                if val == "":
                    out[key.strip()] = {}
                    current_list_key = key.strip()
                else:
                    out[key.strip()] = val.strip("\"'")
        elif current_list_key and stripped.startswith("- "):
            bucket = out[current_list_key]
            if isinstance(bucket, dict):
                item = stripped[2:].strip()
                bucket[item] = True
    return out


def parse_skill_frontmatter(text: str) -> dict:
    """Extract YAML frontmatter (--- ... ---) from a SKILL.md."""
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    if not m:
        return {}
    fm = m.group(1)
    out: dict = {}
    for line in fm.splitlines():
        if ":" in line and not line.startswith((" ", "-", "\t")):
            key, _, val = line.partition(":")
            val = val.strip().strip("\"'")
            if val:
                out[key.strip()] = val
    return out


def load_plugins() -> list[dict]:
    tree = gh_json([f"repos/{REPO}/git/trees/main?recursive=1"])
    names = [e["path"] for e in tree.get("tree", [])
             if e["path"].startswith("plugin-catalog/")
             and e["path"].endswith(".yaml")
             and os.path.basename(e["path"]) not in ("README.yaml", "removed.yaml")]
    plugins = []
    for path in sorted(names):
        text = raw_fetch(path)
        if not text:
            continue
        d = parse_simple_yaml(text)
        caps = d.get("capabilities")
        cap_list = sorted(caps.keys()) if isinstance(caps, dict) else []
        plugins.append({
            "name": d.get("name") or os.path.basename(path)[:-5],
            "repo": d.get("repo", ""),
            "sha": d.get("sha", ""),
            "description": d.get("description", ""),
            "maintainer": d.get("maintainer", ""),
            "tier": d.get("tier", ""),
            "category": d.get("category", ""),
            "docs_url": d.get("docs_url", ""),
            "capabilities": cap_list,
        })
    return plugins


def load_skills() -> list[dict]:
    tree = gh_json([f"repos/{REPO}/git/trees/main?recursive=1"])
    paths = [e["path"] for e in tree.get("tree", [])
             if e["path"].startswith("optional-skills/")
             and e["path"].endswith("SKILL.md")]
    skills = []
    for path in sorted(paths):
        parts = path.split("/")
        category = parts[1] if len(parts) > 2 else ""
        slug = parts[-2] if len(parts) > 2 else ""
        text = raw_fetch(path)
        if not text:
            continue
        fm = parse_skill_frontmatter(text)
        desc = fm.get("description", "")
        if not desc:
            # fall back: first non-heading, non-empty line of the body
            body = re.sub(r"^---.*?---\s*", "", text, flags=re.S)
            for line in body.splitlines():
                s = line.strip()
                if s and not s.startswith("#") and not s.startswith("!["):
                    desc = s[:200]
                    break
        skills.append({
            "slug": slug,
            "category": category,
            "name": fm.get("name", slug.replace("-", " ").title()),
            "description": desc[:300],
            "github_url": f"https://github.com/{REPO}/blob/main/{path}",
        })
    return skills


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    stamp_path = os.path.join(OUT_DIR, ".stamp")
    if os.path.exists(stamp_path):
        age = time.time() - os.path.getmtime(stamp_path)
        if age < REFRESH_SECONDS:
            print(f"ecosystem cache fresh ({int(age/3600)}h old); skip")
            return 0

    t0 = time.time()
    print("loading plugin catalog ...")
    plugins = load_plugins()
    print(f"  {len(plugins)} plugins")

    print("loading optional skills ...")
    skills = load_skills()
    print(f"  {len(skills)} skills")

    payload = {
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "plugins": plugins,
        "skills": skills,
    }
    tmp = os.path.join(OUT_DIR, "ecosystem.json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"))
    os.replace(tmp, os.path.join(OUT_DIR, "ecosystem.json"))

    with open(stamp_path, "w") as fh:
        fh.write(str(int(time.time())))

    print(f"ecosystem: {len(plugins)} plugins, {len(skills)} skills "
          f"in {time.time()-t0:.0f}s -> merge_state/ecosystem/ecosystem.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
