#!/usr/bin/env python3
"""Render the nous-space block row from state.json into index.html.

The row lives between the BLOCKROW markers in index.html; everything else in
that file (nav, CSS, script) stays hand-editable. This script never rewrites
anything outside the markers.

Data:   fetch_state.py -> state.json
Layout: row.css (inlined into index.html's <style>)
Design: mempool.space geometry — see the header of row.css.

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
CSS_START = "/* ROWCSS:START */"
CSS_END = "/* ROWCSS:END */"
N_PER_SIDE = 5
TITLE_MAX = 96

# trailing "(#12345, salvage #67890)" cross-references are always clamped off a
# 125px cube, so drop them from the visible text; the full title stays in title=
CROSSREF = re.compile(r"\s*\([^()]*#\d[^()]*\)\s*$")


def display_title(title: str) -> str:
    text = " ".join((title or "").split())
    while True:
        stripped = CROSSREF.sub("", text)
        if stripped == text:
            return text
        text = stripped


TAG_RE = re.compile(r"^([a-z]+(?:\([^)]+\))?!?):\s*(.+)$", re.S)


def split_title(title: str) -> tuple[str, str]:
    """('fix(desktop)', 'removing or re-pointing a connection ...').

    The scope tag gets its own tiny line so the two description lines carry real
    words instead of spending a third of the width on 'fix(desktop):'.
    """
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


def cube(item: dict, kind: str) -> str:
    """kind: p-green (awaiting merge) | p-blue (merged to main)"""
    n = item["number"]
    tag, desc = split_title(item["title"])
    tag_html = f'\n          <div class="g">{esc(tag)}</div>' if tag else ""
    tail = (f'idle {esc(item["ago"])}' if kind == "p-green"
            else f'merged {esc(item["ago"])}')
    return f"""      <a class="cube {kind}" href="{item['url']}" target="_blank" rel="noopener" title="#{n} {esc(item['title'])}">
        <div class="face">
          <div class="n">#{n}</div>
          <div class="d"><span class="add">+{item['additions']}</span> <span class="del">-{item['deletions']}</span></div>{tag_html}
          <div class="t">{esc(clip(desc))}</div>
          <div class="w">{tail}</div>
        </div>
      </a>"""


def merged_cell(item: dict) -> str:
    """Merged block plus the prominent name box underneath (mempool badge.miner-name)."""
    mine = "mine" if item.get("mine") else ""
    return f"""      <div class="wrap">
{cube(item, 'p-blue')}
        <div class="miner"><a class="{mine}" href="https://github.com/{esc(item['author'])}" target="_blank" rel="noopener" title="author: {esc(item['author'])}">{esc(item['author'])}</a></div>
      </div>"""


def render_row(state: dict) -> str:
    # strongest pending PR sits nearest the divider, so render the list reversed
    pending = list(reversed(state["pending"][:N_PER_SIDE]))
    merged = state["merged"][:N_PER_SIDE]
    greens = "\n".join(cube(p, "p-green") for p in pending)
    blues = "\n".join(merged_cell(x) for x in merged)
    return f"""  <div class="blockrow">
    <div class="col pending">
      <div class="cluster">
{greens}
      </div>
    </div>

    <div class="split"></div>

    <div class="col merged">
      <div class="cluster">
{blues}
      </div>
    </div>
  </div>"""


def main() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    page = INDEX.read_text(encoding="utf-8")
    for marker in (START, END, CSS_START, CSS_END):
        if marker not in page:
            raise SystemExit(f"ERROR: marker {marker} missing from index.html")

    # row.css is the single source of truth for the row layout: re-inline it on
    # every build so editing the CSS alone is enough to publish a change.
    ci = page.index(CSS_START) + len(CSS_START)
    cj = page.index(CSS_END)
    page = page[:ci] + "\n" + (ROOT / "row.css").read_text(encoding="utf-8") + page[cj:]

    i = page.index(START) + len(START)
    j = page.index(END)
    new = page[:i] + "\n" + render_row(state) + "\n  " + page[j:]

    if new == page:
        print("index.html unchanged")
        return 0
    INDEX.write_text(new, encoding="utf-8")
    pend = ", ".join(f"#{p['number']}" for p in state["pending"][:N_PER_SIDE])
    merg = ", ".join(f"#{x['number']}" for x in state["merged"][:N_PER_SIDE])
    print(f"index.html rendered — green: {pend} | blue: {merg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
