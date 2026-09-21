#!/usr/bin/env python3
"""Render the nous-space block row + below-row panels from state.json into index.html.

The row lives between the BLOCKROW markers, panels between PANELS markers,
and CSS between ROWCSS markers. Everything else in index.html (nav, etc.)
stays hand-editable.

Data:   fetch_state.py -> state.json
Layout: row.css (inlined into index.html's <style>)
Design: mempool.space geometry.

Usage:  python3 fetch_state.py && python3 build.py
"""
from __future__ import annotations

import html
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent
STATE = ROOT / "state.json"
INDEX = ROOT / "index.html"

START = "<!-- BLOCKROW:START -->"
END = "<!-- BLOCKROW:END -->"
PANELS_START = "<!-- PANELS:START -->"
PANELS_END = "<!-- PANELS:END -->"
CSS_START = "/* ROWCSS:START */"
CSS_END = "/* ROWCSS:END */"
N_PER_SIDE = 5
N_MERGED_SHOW = 15  # enough blocks to make the scrollable strip work
TITLE_MAX = 96

# trailing "(#12345, salvage #67890)" cross-references drop for display
CROSSREF = re.compile(r"\s*\([^()]*#\d[^()]*\)\s*$")
TAG_RE = re.compile(r"^([a-z]+(?:\([^)]+\))?!?):\s*(.+)$", re.S)


def display_title(title: str) -> str:
    text = " ".join((title or "").split())
    while True:
        stripped = CROSSREF.sub("", text)
        if stripped == text:
            return text
        text = stripped


def split_title(title: str) -> tuple[str, str]:
    text = display_title(title)
    m = TAG_RE.match(text)
    if not m:
        return "", text
    return m.group(1), m.group(2)


def clip(text: str, limit: int = TITLE_MAX) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "\u2026"


def esc(text: str) -> str:
    return html.escape(text or "", quote=True)


# ── cube ────────────────────────────────────────────────────────────────────
# PR number sits in a pill ABOVE the cube, not inside the face.  The face gets
# more room for the description.

def number_pill(n: int, kind: str) -> str:
    cls = "p-num-green" if kind == "p-green" else "p-num-blue"
    return f'<span class="p-num {cls}">#{n}</span>'


def cube(item: dict, kind: str) -> str:
    n = item["number"]
    tag, desc = split_title(item["title"])
    tag_html = f'\n          <div class="g">{esc(tag)}</div>' if tag else ""
    tail = (f'idle {esc(item["ago"])}' if kind == "p-green"
            else f'merged {esc(item["ago"])}')
    return f"""      <div class="wrap">
        {number_pill(n, kind)}
        <a class="cube {kind}" href="{item['url']}" target="_blank" rel="noopener" title="#{n} {esc(item['title'])}">
          <div class="face">
            <div class="d"><span class="add">+{item['additions']}</span> <span class="del">-{item['deletions']}</span></div>{tag_html}
            <div class="t">{esc(clip(desc))}</div>
            <div class="w">{tail}</div>
          </div>
        </a>
      </div>"""


def merged_cell(item: dict) -> str:
    """Merged block + name box under the cube."""
    mine = "mine" if item.get("mine") else ""
    return f"""      <div class="wrap">
        {number_pill(item['number'], 'p-blue')}
        <a class="cube p-blue" href="{item['url']}" target="_blank" rel="noopener" title="#{item['number']} {esc(item['title'])}">
          <div class="face">
            <div class="d"><span class="add">+{item['additions']}</span> <span class="del">-{item['deletions']}</span></div>
            <div class="g">{esc(split_title(item['title'])[0])}</div>
            <div class="t">{esc(clip(split_title(item['title'])[1]))}</div>
            <div class="w">merged {esc(item['ago'])}</div>
          </div>
        </a>
        <div class="miner"><a class="{mine}" href="https://github.com/{esc(item['author'])}" target="_blank" rel="noopener" title="author: {esc(item['author'])}">{esc(item['author'])}</a></div>
      </div>"""


# ── row ─────────────────────────────────────────────────────────────────────
# One continuous scrollable strip: green pending blocks, divider, blue merged
# blocks. Scroll to see history.

def render_row(state: dict) -> str:
    pending = list(reversed(state["pending"][:N_PER_SIDE]))
    merged = state["merged"][:N_MERGED_SHOW]
    greens = "\n".join(cube(p, "p-green") for p in pending)
    blues = "\n".join(merged_cell(x) for x in merged)
    return f"""  <div class="stripscroll">
    <div class="strip">
      {greens}
      <div class="split"></div>
      {blues}
    </div>
  </div>"""


# ── below-row panels ────────────────────────────────────────────────────────

def backlog_panel(state: dict) -> str:
    bl = state.get("backlog", {})
    total = bl.get("total_open", 0)
    oldest = bl.get("oldest_pr")
    newest = bl.get("newest_pr")
    areas = bl.get("areas", {})

    oldest_html = ""
    if oldest:
        oldest_html = f"""        <div class="stat-row">
          <span class="stat-label">oldest</span>
          <a class="stat-val" href="https://github.com/{state['repo']}/pull/{oldest['number']}" target="_blank" rel="noopener">#{oldest['number']}</a>
          <span class="stat-dim">{oldest['age_days']}d ago</span>
        </div>"""
    newest_html = ""
    if newest:
        newest_html = f"""        <div class="stat-row">
          <span class="stat-label">newest</span>
          <a class="stat-val" href="https://github.com/{state['repo']}/pull/{newest['number']}" target="_blank" rel="noopener">#{newest['number']}</a>
          <span class="stat-dim">{newest['age_hours']}h ago</span>
        </div>"""

    # area breakdown as small pill badges
    area_pills = ""
    for a, c in list(areas.items())[:8]:
        area_pills += f"""<span class="area-pill">{esc(a)} {c}</span>"""

    return f"""    <div class="dash-card left">
      <h3>PR Backlog</h3>
      <div class="big-num">{total:,}</div>
      <div class="big-sub">open pull requests</div>
      {newest_html}
      {oldest_html}
      <div class="section-label">by area</div>
      <div class="area-cloud">
        {area_pills}
      </div>
    </div>"""


def releases_panel(state: dict) -> str:
    rl = state.get("releases", {})
    rels = rl.get("releases", [])
    cadence = rl.get("cadence_days")
    latest = rl.get("latest")

    latest_html = ""
    if latest:
        latest_html = f"""        <div class="stat-row">
          <span class="stat-label">latest</span>
          <span class="stat-val">{esc(latest['tagName'])}</span>
        </div>"""

    cadence_html = f"""        <div class="stat-row">
          <span class="stat-label">cadence</span>
          <span class="stat-val">~{cadence}d</span>
          <span class="stat-dim">3 releases in 2 weeks</span>
        </div>""" if cadence else ""

    # release timeline dots
    dots = ""
    for r in rels[:12]:
        dots += f'<span class="rel-dot" title="{esc(r["tag"])} ({esc(r["date"])})"></span>'

    # merge velocity
    mv = state.get("merge_velocity", {})
    velo_rows = ""
    for area, v in list(mv.items())[:6]:
        velo_rows += f"""          <div class="velo-row">
            <span class="velo-area">{esc(area)}</span>
            <span class="velo-h">{v['avg_hours']}h</span>
            <span class="velo-n">({v['count']})</span>
          </div>"""

    return f"""    <div class="dash-card right">
      <h3>Release Velocity</h3>
      {latest_html}
      {cadence_html}
      <div class="section-label">release timeline</div>
      <div class="rel-dots">
        {dots}
      </div>
      <div class="section-label">merge speed by area</div>
      <div class="velo-list">
{velo_rows}
      </div>
    </div>"""


def render_panels(state: dict) -> str:
    return f"""  <div class="dash-row">
{backlog_panel(state)}
{releases_panel(state)}
  </div>"""


# ── main ────────────────────────────────────────────────────────────────────

def main() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    page = INDEX.read_text(encoding="utf-8")

    # check all markers
    for marker in (START, END, PANELS_START, PANELS_END, CSS_START, CSS_END):
        if marker not in page:
            raise SystemExit(f"ERROR: marker {marker} missing from index.html")

    # re-inline row.css
    ci = page.index(CSS_START) + len(CSS_START)
    cj = page.index(CSS_END)
    page = page[:ci] + "\n" + (ROOT / "row.css").read_text(encoding="utf-8") + page[cj:]

    # block row
    ri = page.index(START) + len(START)
    rj = page.index(END)
    page = page[:ri] + "\n" + render_row(state) + "\n  " + page[rj:]

    # below-row panels
    pi = page.index(PANELS_START) + len(PANELS_START)
    pj = page.index(PANELS_END)
    page = page[:pi] + "\n" + render_panels(state) + "\n  " + page[pj:]

    if page == INDEX.read_text(encoding="utf-8"):
        print("index.html unchanged")
        return 0

    INDEX.write_text(page, encoding="utf-8")
    pend = ", ".join(f"#{p['number']}" for p in state["pending"][:N_PER_SIDE])
    merg = ", ".join(f"#{x['number']}" for x in state["merged"][:N_PER_SIDE])
    print(f"index.html rendered — green: {pend} | blue: {merg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())