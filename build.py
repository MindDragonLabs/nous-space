#!/usr/bin/env python3
"""Render the nous-space block row from state.json.

Outputs variants.html — the same row in three layout stances, so one can be
picked by eye instead of by description.

Tokens, cube geometry and skew angles are copied from mempool.space source
(frontend/src/app/components/{mempool-blocks,blockchain-blocks}/...scss), so the
look is parity-by-construction rather than imitation.

Usage:  python3 fetch_state.py && python3 build.py
"""
from __future__ import annotations

import datetime as dt
import html
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
STATE = ROOT / "state.json"
INDEX = ROOT / "index.html"
OUT = ROOT / "variants.html"

GITHUB = "https://github.com/{owner_repo}/pull/{n}"


def between(text: str, start: str, end: str) -> str:
    i = text.index(start) + len(start)
    j = text.index(end, i)
    return text[i:j]


# ---------------------------------------------------------------- mempool tokens
MEMPOOL_CSS = """
/* ===== tokens copied verbatim from mempool.space frontend/src/styles.scss ===== */
:root {
  --mp-bg: #11131f;
  --mp-active-bg: #000000;
  --mp-hover-bg: #12131e;
  --mp-fg: #fff;
  --mp-info: #00ddff;
  --mp-box-bg: #171c2a;
  --mp-stat-box-bg: #0b1018;
  --mp-border-subtle: rgba(255, 255, 255, 0.11);
  --block-top: #232838;          /* blue cube top face   */
  --block-side: #191c27;         /* blue cube side face  */
  --mempool-block-top: #403834;  /* green cube top face  */
  --mempool-block-side: #2d2825; /* green cube side face */
  --mempool-block-loading: #554b45;
  --mp-green: #83fd00;
  --mp-red: #ff3d00;
  --mp-yellow: #fff000;
  --mp-grey: #7e7e7e;
  --mp-orange: #ff9f00;
  --mp-purple: #9339f4;
}

/* ===== geometry copied from blockchain-blocks.component.scss =====
   .bitcoin-block::after  { width:bs;        height:calc(.192*bs); top:calc(-.192*bs);
                            left:calc(-.16*bs); background:var(--block-top);  transform:skew(40deg);  origin:top }
   .bitcoin-block::before { width:calc(.16*bs); height:bs;          top:calc(-.096*bs);
                            left:calc(-.16*bs); background:var(--block-side); transform:skewY(50deg); origin:top }
   Both clusters are 125px with a 30px gap in mempool; --block-size drives everything. */
:root {
  --block-size: clamp(96px, 9vw, 125px);
  --block-gap: calc(0.24 * var(--block-size));
}

.lookbook { background: var(--mp-bg); min-height: 100vh; padding: 0 0 90px 0; }
.lb-head { padding: 26px 26px 8px 26px; font-family: var(--mono); }
.lb-head h1 { font-size: 17px; letter-spacing: .18em; color: var(--mp-info); font-weight: 700; }
.lb-head p { margin-top: 8px; font-size: 12px; color: var(--mp-grey); line-height: 1.6; max-width: 900px; font-family: var(--font); }
.lb-head code { color: var(--mp-orange); }

.stance { border-top: 1px solid var(--mp-border-subtle); margin-top: 26px; padding-top: 18px; }
.stance-head { padding: 0 26px 4px 26px; font-family: var(--mono); display: flex; align-items: baseline; gap: 12px; }
.stance-tag { font-size: 12px; font-weight: 700; color: #000; background: var(--mp-green); padding: 2px 8px; border-radius: 3px; letter-spacing: .06em; }
.stance-name { font-size: 14px; color: #fff; font-weight: 700; letter-spacing: .05em; }
.stance-why { font-size: 12px; color: var(--mp-grey); font-family: var(--font); }
.stance-note { padding: 8px 26px 0 26px; font-size: 11.5px; color: var(--mp-grey); font-family: var(--mono); }

.blockrow {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 26px;
  padding: 34px 26px 30px 46px;   /* room for the 24px-tall top face + 20px side face */
  overflow: hidden;
}
.col { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
.cluster { display: flex; align-items: flex-start; gap: var(--block-gap); }

.cap {
  display: none;
  font-family: var(--mono); font-size: 11px; letter-spacing: .14em;
  color: var(--mp-grey); padding-left: 2px;
}
.v2 .cap { display: block; }
.cap.pending { color: var(--mp-green); }
.cap.merged { color: var(--mp-info); }

/* ---- cube (mempool projected-block geometry, 3D faces) ---- */
.cube {
  position: relative;
  width: var(--block-size);
  height: var(--block-size);
  flex-shrink: 0;
  display: block;
  text-decoration: none;
  transition: transform .18s ease;
}
.cube:hover { transform: translateY(-4px); }
.cube:focus-visible { outline: 2px solid var(--mp-yellow); outline-offset: 3px; }

.cube::before {                       /* side face — skewY(50deg) */
  content: '';
  width: calc(0.16 * var(--block-size));
  height: var(--block-size);
  position: absolute;
  top: calc(-0.096 * var(--block-size));
  left: calc(-0.16 * var(--block-size));
  background-color: var(--face-side);
  z-index: -1;
  transform: skewY(50deg);
  transform-origin: top;
  transition: transform 1s, left 1s;
}
.cube::after {                        /* top face — skew(40deg) */
  content: '';
  width: var(--block-size);
  height: calc(0.192 * var(--block-size));
  position: absolute;
  top: calc(-0.192 * var(--block-size));
  left: calc(-0.16 * var(--block-size));
  background-color: var(--face-top);
  transform: skew(40deg);
  transform-origin: top;
  transition: transform 1s, left 1s;
}

.cube.p-green { --face-side: var(--mempool-block-side); --face-top: var(--mempool-block-top); }
.cube.p-blue  { --face-side: var(--block-side);         --face-top: var(--block-top); }

/* front faces: mempool green = brown slice + green fee bands; blue = indigo -> purple -> blue */
.cube.p-green .face {
  background:
    linear-gradient(90deg,
      var(--mempool-block-loading) 0 7%,
      #006b34 7% 22%,
      #007d3d 22% 55%,
      #008a44 55% 100%);
}
.cube.p-blue .face {
  background: linear-gradient(180deg, #272f4e 0%, #9339f4 3%, #007cfa 100%);
}

.face {
  position: relative;
  z-index: 2;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  text-align: center;
  padding: calc(0.06 * var(--block-size));
  font-family: var(--mono);
  overflow: hidden;
}
.face .l1 { font-size: calc(0.128 * var(--block-size)); font-weight: 700; color: #fff; line-height: 1.1; }
.face .l2 { font-size: calc(0.096 * var(--block-size)); margin-top: calc(0.03 * var(--block-size)); }
.face .l3 { font-size: calc(0.088 * var(--block-size)); color: rgba(255,255,255,.86); margin-top: calc(0.014 * var(--block-size)); }
.face .l4 { font-size: calc(0.080 * var(--block-size)); color: rgba(255,255,255,.72); margin-top: calc(0.014 * var(--block-size)); white-space: nowrap; }
.face .l5 { font-size: calc(0.104 * var(--block-size)); color: rgba(255,255,255,.92); margin-top: calc(0.026 * var(--block-size)); }
.cube.p-green .face .l5 { color: var(--mp-green); }
.cube.p-blue .face .l5  { color: var(--mp-info); }
.face .add { color: var(--mp-green); }
.face .del { color: var(--mp-red); }
.cube.p-green .face .add { color: #c9ffa0; }
.cube.p-green .face .del { color: #ffb0a0; }
.face .l4.ready { color: var(--mp-yellow); }

/* ---- divider: 2px dashed line + up arrow (mempool #arrow-up) ---- */
.split {
  flex: 0 0 auto;
  align-self: center;
  width: 2px;
  height: calc(1.6 * var(--block-size));
  background-image: repeating-linear-gradient(180deg,
      rgba(255,255,255,.42) 0 6px, rgba(0,0,0,0) 6px 12px);
  position: relative;
  margin-top: calc(-0.2 * var(--block-size));
}
.split::after {
  content: '';
  position: absolute;
  left: -5px;
  bottom: calc(-0.16 * var(--block-size));
  width: 0; height: 0;
  border-left: 6px solid transparent;
  border-right: 6px solid transparent;
  border-bottom: 9px solid #fff;
}
.split .now {
  display: none;
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  background: var(--mp-bg);
  border: 1px solid var(--mp-border-subtle);
  color: var(--mp-yellow);
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: .12em;
  padding: 3px 6px;
  border-radius: 3px;
  white-space: nowrap;
}
.v3 .split .now { display: block; }

/* v3 reads as a full-bleed scrolling strip: edges fade out */
.v3 .blockrow { padding-left: 0; padding-right: 0; }
.v3 .col.pending { mask-image: linear-gradient(90deg, transparent 0, #000 9%); -webkit-mask-image: linear-gradient(90deg, transparent 0, #000 9%); }
.v3 .col.merged  { mask-image: linear-gradient(270deg, transparent 0, #000 9%); -webkit-mask-image: linear-gradient(270deg, transparent 0, #000 9%); }

.lb-foot { padding: 22px 26px 0 26px; font-family: var(--mono); font-size: 11.5px; color: var(--mp-grey); line-height: 1.7; }
.lb-foot b { color: #fff; font-weight: 600; }
"""

NAV_SCRIPT = """
function toggleDropdown() {
  document.getElementById('branchDropdown').classList.toggle('open');
}
function selectBranch(name) {
  document.getElementById('currentBranch').textContent = name;
  document.getElementById('branchDropdown').classList.remove('open');
}
document.addEventListener('click', function(e) {
  if (!e.target.closest('.dropdown-wrapper')) {
    document.getElementById('branchDropdown').classList.remove('open');
  }
});
document.querySelectorAll('.nav-icon').forEach(icon => {
  icon.addEventListener('click', function() {
    document.querySelectorAll('.nav-icon').forEach(i => i.classList.remove('active'));
    this.classList.add('active');
  });
});
"""


def cube(item: dict, kind: str, repo: str) -> str:
    n = item["number"]
    title = html.escape(item.get("title") or "", quote=True)
    url = GITHUB.format(owner_repo=repo, n=n)
    if kind == "p-green":
        label_class = "ready" if item.get("score", 0) >= 9 else ""
        l4 = f'<div class="l4 {label_class}">{html.escape(item.get("label",""))}</div>'
        l5 = f'<div class="l5">idle {html.escape(item.get("ago",""))}</div>'
    else:
        l4 = f'<div class="l4">{html.escape(item.get("author",""))}</div>'
        l5 = f'<div class="l5">merged {html.escape(item.get("ago",""))}</div>'
    commits = item.get("commits") or 0
    files = item.get("changedFiles") or 0
    return f"""        <a class="cube {kind}" href="{url}" target="_blank" rel="noopener" title="#{n} {title}">
          <div class="face">
            <div class="l1">#{n}</div>
            <div class="l2"><span class="add">+{item.get('additions',0)}</span> <span class="del">-{item.get('deletions',0)}</span></div>
            <div class="l3">{commits}c · {files}f</div>
            {l4}
            {l5}
          </div>
        </a>"""


def cluster(items: list[dict], kind: str, repo: str) -> str:
    return "\n".join(cube(i, kind, repo) for i in items)


def stance(tag: str, ident: str, name: str, why: str, note: str,
           pending: list[dict], merged: list[dict], repo: str) -> str:
    # nearest the divider = next to land, so the strongest pending PR renders last (rightmost)
    pend = list(reversed(pending))
    return f"""
<section class="stance {ident}">
  <div class="stance-head">
    <span class="stance-tag">{tag}</span>
    <span class="stance-name">{name}</span>
    <span class="stance-why">{why}</span>
  </div>
  <div class="stance-note">{note}</div>
  <div class="blockrow">
    <div class="col pending">
      <div class="cap pending">awaiting merge</div>
      <div class="cluster">
{cluster(pend, 'p-green', repo)}
      </div>
    </div>
    <div class="split"><span class="now">NOW</span></div>
    <div class="col merged">
      <div class="cap merged">merged to main</div>
      <div class="cluster">
{cluster(merged, 'p-blue', repo)}
      </div>
    </div>
  </div>
</section>"""


def main() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    index = INDEX.read_text(encoding="utf-8")

    base_css = between(index, "<style>", "</style>")
    nav = between(index, '<nav class="topnav">', "</nav>") + "</nav>"
    repo = state["repo"]
    gen = state["generated"]

    pending = state["pending"][:6]
    merged = state["merged"][:6]

    body = "".join([
        stance("V1", "v1", "mempool exact", "no labels — the two colours carry the meaning",
               "green cluster = open PRs, strongest nearest the divider · blue cluster = already merged · "
               "125px cubes, 30px gaps, skewY(50deg) side + skew(40deg) top, mempool face colours",
               pending[:4], merged[:4], repo),
        stance("V2", "v2", "labelled", "same cubes, each cluster named so a first-time reader gets it",
               "identical geometry and tokens to V1 · adds 'AWAITING MERGE' / 'MERGED TO MAIN' captions · 5 cubes per side",
               pending[:5], merged[:5], repo),
        stance("V3", "v3", "now marker + full-bleed strip", "reads as a live strip: edges fade, the divider is NOW",
               "6 cubes per side · left/right edges masked so it implies more behind · a NOW pill sits on the divider",
               pending, merged, repo),
    ])

    html_out = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NOUS SPACE — block row variants</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@3.47.0/dist/tabler-icons.min.css">
<style>
{base_css}
{MEMPOOL_CSS}
</style>
</head>
<body>
<nav class="topnav">
{nav}
</nav>

<div class="lookbook">
  <div class="lb-head">
    <h1>NOUS SPACE — BLOCK ROW VARIANTS</h1>
    <p>Same data, same mempool.space geometry, three layouts. Green = open PRs awaiting merge
    (strongest nearest the divider). Blue = PRs already merged to <code>main</code> (newest nearest the divider).
    Real live data from <code>{repo}</code>, generated <code>{gen}</code>.
    Files: <code>fetch_state.py</code> → <code>state.json</code> → <code>build.py</code>.</p>
  </div>
{body}
  <div class="lb-foot">
    <b>Pick one: V1, V2, or V3</b> — or mix (for example V1 cubes with V2 captions).<br>
    Numbers on each cube: pull request · added/removed lines · commits and files · readiness (green) or author (blue) · age.<br>
    Cubes are links to the real PRs; hover for the title. Block size scales with the viewport, so the whole row fits a narrow pane
    and reaches the exact 125px at full width.
  </div>
</div>

<script>
{NAV_SCRIPT}
</script>
</body>
</html>
"""
    OUT.write_text(html_out, encoding="utf-8")
    print(f"wrote {OUT.name} ({len(html_out)} bytes): 6 pending / 6 merged from {repo}")
    print("open: http://127.0.0.1:8791/variants.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
