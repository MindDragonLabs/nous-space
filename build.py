#!/usr/bin/env python3
"""Render the nous-space block row + below-row panels from state.json into index.html.

The row lives between the BLOCKROW markers, panels between PANELS markers,
CSS between ROWCSS markers, and the client catalog between APPDATA markers.
Everything else in index.html (nav, etc.) stays hand-editable.

Data:   fetch_state.py -> state.json
Layout: row.css (inlined into index.html's <style>)
Design: mempool.space geometry.

Usage:  python3 fetch_state.py && python3 build.py
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent
STATE = ROOT / "state.json"
INDEX = ROOT / "index.html"

START = "<!-- BLOCKROW:START -->"
END = "<!-- BLOCKROW:END -->"
PANELS_START = "<!-- PANELS:START -->"
PANELS_END = "<!-- PANELS:END -->"
TICKER_START = "<!-- TICKER:START -->"
TICKER_END = "<!-- TICKER:END -->"
NEWSLETTER_START = "<!-- NEWSLETTER:START -->"
NEWSLETTER_END = "<!-- NEWSLETTER:END -->"
ISSUES_START = "<!-- ISSUES:START -->"
ISSUES_END = "<!-- ISSUES:END -->"
PRS_START = "<!-- PRS:START -->"
PRS_END = "<!-- PRS:END -->"
CONTRIBUTORS_START = "<!-- CONTRIBUTORS:START -->"
CONTRIBUTORS_END = "<!-- CONTRIBUTORS:END -->"
PRARCHIVE_START = "<!-- PRARCHIVE:START -->"
PRARCHIVE_END = "<!-- PRARCHIVE:END -->"
ECOSYSTEM_START = "<!-- ECOSYSTEM:START -->"
ECOSYSTEM_END = "<!-- ECOSYSTEM:END -->"
QUALITY_START = "<!-- QUALITY:START -->"
QUALITY_END = "<!-- QUALITY:END -->"
APPDATA_START = "<!-- APPDATA:START -->"
APPDATA_END = "<!-- APPDATA:END -->"
CSS_START = "/* ROWCSS:START */"
CSS_END = "/* ROWCSS:END */"
N_PER_SIDE = 5
N_MERGED_SHOW = 30
NEWS_HTML_ROWS = 60  # rest of the 48h wire loads from news.json
NEWS_HEAD_ROWS = 150  # data/news-head.json — what the live poll fetches  # enough blocks to overflow any viewport width
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
    return f"""  <div class="stripscroll" id="blockstrip" tabindex="0" role="region"
       aria-label="Pull request strip: green blocks are open pull requests the maintainer is involved in; blue blocks are merged. Use arrow keys to scroll.">
    <div class="strip">
      {greens}
      <div class="split" aria-hidden="true"></div>
      {blues}
    </div>
  </div>
  <details class="strip-note">
    <summary>How the green strip is ordered</summary>
    <p>Green blocks are open pull requests the maintainer is involved in. Their order considers these factors:</p>
    <ul>
      <li>CI check results (tests)</li>
      <li>review state — approved, changes requested, or none yet</li>
      <li>merge conflicts</li>
      <li>draft status</li>
    </ul>
    <p>Diff size is shown on each block but does not change the order. This is a reading aid, not a forecast.</p>
  </details>
  <script>
// Drag-to-scroll (mempool.space behaviour)
(function(){{
  const el = document.getElementById('blockstrip');
  if (!el) return;
  let down = false, sx = 0, sl = 0;
  el.addEventListener('mousedown', function(e){{
    if (e.target.closest('a')) return;           // let links through
    down = true;
    sx = e.pageX - el.offsetLeft;
    sl = el.scrollLeft;
    el.style.cursor = 'grabbing';
    el.style.scrollBehavior = 'auto';
    e.preventDefault();
  }});
  el.addEventListener('mouseleave', function(){{
    down = false;
    el.style.cursor = 'grab';
  }});
  el.addEventListener('mouseup', function(){{
    down = false;
    el.style.cursor = 'grab';
  }});
  el.addEventListener('mousemove', function(e){{
    if (!down) return;
    e.preventDefault();
    el.scrollLeft = sl - (e.pageX - el.offsetLeft - sx);
  }});
  // touch support
  el.addEventListener('touchstart', function(e){{
    if (e.target.closest('a')) return;
    down = true;
    sx = e.touches[0].pageX - el.offsetLeft;
    sl = el.scrollLeft;
    el.style.scrollBehavior = 'auto';
  }}, {{passive: false}});
  el.addEventListener('touchend', function(){{ down = false; }});
  el.addEventListener('touchmove', function(e){{
    if (!down) return;
    el.scrollLeft = sl - (e.touches[0].pageX - el.offsetLeft - sx);
  }}, {{passive: false}});
}})();
  </script>"""


# ── below-row panels ────────────────────────────────────────────────────────

def backlog_panel(state: dict) -> str:
    bl = state.get("backlog", {})
    total = bl.get("total_open", 0)
    oldest = bl.get("oldest_pr")
    newest = bl.get("newest_pr")

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

    # ── lane counts: three different scopes, each labelled explicitly ──
    q = _as_dict(state.get("quality"))
    counts = _as_dict(q.get("counts"))
    lane_open = state.get("open_in_maintainer_lane") or 0
    watch_tracked = counts.get("watch_tracked") or q.get("tracked_open") or 0
    maintainer = state.get("maintainer") or "the maintainer"

    def lane_row(label: str, value, dim: str, api: str) -> str:
        return (f'        <div class="stat-row">\n'
                f'          <span class="stat-label">{esc(label)}</span>\n'
                f'          <span class="stat-val" data-api="{api}">{value:,}</span>\n'
                f'          <span class="stat-dim">{esc(dim)}</span>\n'
                f'        </div>')

    lane_html = "\n".join([
        lane_row("watch", watch_tracked, "whole maintainer team", "lane.watch_tracked"),
        lane_row("lane", lane_open, f"involving {maintainer}", "lane.lane_open"),
    ])

    # ── line chart: new PRs per day over last 7 days ──
    daily = bl.get("daily_new", [])
    chart_svg = _daily_line_chart(daily) if daily else ""

    return f"""    <div class="dash-card left">
      <h3><i class="hgi hgi-stroke hgi-inbox" aria-hidden="true"></i> PR Backlog {fresh_stamp(state, "backlog", api=True)}</h3>
      <div class="big-num">{total:,}</div>
      <div class="big-sub">open PRs in the repo</div>
      <div class="section-label">lane counts</div>
      {lane_html}
      {newest_html}
      {oldest_html}
      <div class="section-label">new PRs, all authors — last 7 days</div>
      {chart_svg}
    </div>"""


def _daily_line_chart(daily: list[dict]) -> str:
    """Render a sparkline SVG for daily new PR counts."""
    counts = [d["count"] for d in daily]
    if not counts:
        return ""
    max_c = max(counts) or 1
    w, h = 240, 80
    pad_left, pad_bottom, pad_top = 24, 16, 8
    gw = w - pad_left - 4
    gh = h - pad_bottom - pad_top
    n = len(counts)

    # points
    pts = ""
    for i, c in enumerate(counts):
        x = pad_left + (gw * i / (n - 1)) if n > 1 else pad_left + gw / 2
        y = pad_top + gh - (gh * c / max_c)
        pts += f"{x:.1f},{y:.1f} "

    # area fill under the line
    area_pts = f"{pad_left:.1f},{pad_top + gh:.1f} " + pts + f"{pad_left + gw:.1f},{pad_top + gh:.1f}"

    # labels — date short (MM-DD) under each point
    labels = ""
    for i, d in enumerate(daily):
        short = d["date"][5:]  # "MM-DD"
        x = pad_left + (gw * i / (n - 1)) if n > 1 else pad_left + gw / 2
        y = h - 2
        labels += f'<text x="{x:.1f}" y="{y:.0f}" class="chart-label">{short}</text>'

    return f"""<svg class="line-chart" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="New pull requests per day, last {n} days: {', '.join(str(c) for c in counts)}">
  <polygon points="{area_pts}" fill="url(#fade)"/>
  <defs><linearGradient id="fade" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="var(--nous-amber)" stop-opacity="0.25"/>
    <stop offset="100%" stop-color="var(--nous-amber)" stop-opacity="0.02"/>
  </linearGradient></defs>
  <polyline points="{pts}" fill="none" stroke="var(--nous-amber)" stroke-width="1.5" vector-effect="non-scaling-stroke"/>
  {labels}
</svg>"""


def _day_label(iso: str) -> str:
    try:
        when = dt.datetime.strptime(iso, "%Y-%m-%d")
    except (TypeError, ValueError):
        return iso or ""
    return f"{when.strftime('%b')} {when.day}"


def merge_rate_panel(state: dict) -> str:
    mr = state.get("merge_rate", {})
    rows = ""
    for period in ["7d", "30d", "90d"]:
        if period in mr and isinstance(mr[period], dict) and "per_day" in mr[period]:
            r = mr[period]
            rows += f"""        <div class="stat-row">
          <span class="stat-label">{period}</span>
          <span class="stat-val">{r['per_day']} PR/day</span>
          <span class="stat-dim">{r['count']} merged</span>
        </div>"""
    if mr.get("high_day") or mr.get("low_day"):
        rows += """        <div class="section-label">high and low day · last 90 days</div>\n"""
    for key, label in (("high_day", "high"), ("low_day", "low")):
        day = mr.get(key) or {}
        if not isinstance(day, dict) or "count" not in day:
            continue
        rows += f"""        <div class="stat-row">
          <span class="stat-label">{label}</span>
          <span class="stat-val">{int(day['count'])} PRs</span>
          <span class="stat-dim">{esc(_day_label(day.get('date', '')))}</span>
        </div>"""

    # merge speed by area (moved here from releases panel)
    mv = state.get("merge_velocity", {})
    velo_rows = ""
    for area, v in list(mv.items())[:6]:
        velo_rows += f"""          <div class="velo-row">
            <span class="velo-area">{esc(area)}</span>
            <span class="velo-h">{v['avg_hours']}h</span>
            <span class="velo-n">({v['count']})</span>
          </div>"""

    return f"""    <div class="dash-card third">
      <h3><i class="hgi hgi-stroke hgi-activity-01" aria-hidden="true"></i> PR Velocity {fresh_stamp(state, "velocity")}</h3>
{rows}
      <div class="section-label">merge speed by area</div>
      <div class="velo-list">
{velo_rows}
      </div>
    </div>"""


def releases_panel(state: dict) -> str:
    rl = state.get("releases", {})
    rels = rl.get("releases", [])
    cadence = rl.get("cadence_days")
    latest = rl.get("latest")
    calendar = rl.get("calendar", [])

    latest_html = ""
    if latest:
        ver = latest.get("version", "") or latest.get("tag", "")
        import re as _re
        m = _re.search(r'(v\d+\.\d+\.\d+)', ver)
        display = m.group(1) if m else ver
        date_tag = latest.get("tag", "")
        latest_html = f"""        <div class="stat-row">
          <span class="stat-label">latest</span>
          <span class="stat-val">{esc(display)}</span>
          <span class="stat-dim">{esc(date_tag)}</span>
        </div>"""

    recent_fortnight = sum(1 for rel in rels if isinstance(rel, dict) and (rel.get("days_ago") or 99) <= 14)
    cadence_html = f"""        <div class="stat-row">
          <span class="stat-label">cadence</span>
          <span class="stat-val">~{cadence}d</span>
          <span class="stat-dim">{recent_fortnight} releases in 2 weeks</span>
        </div>""" if cadence else ""

    # ── 30-day calendar grid ──
    cal_html = _release_calendar(calendar)

    return f"""    <div class="dash-card right">
      <h3><i class="hgi hgi-stroke hgi-rocket-01" aria-hidden="true"></i> Release Velocity {fresh_stamp(state, "releases")}</h3>
      {latest_html}
      {cadence_html}
      <div class="section-label">releases — last 30 days</div>
      {cal_html}
    </div>"""


def _release_calendar(calendar: list[dict]) -> str:
    """Render a GitHub-style contribution calendar for releases."""
    max_count = max((c["count"] for c in calendar), default=0)
    cells = ""
    for c in calendar:
        day = c["date"][-2:].lstrip("0")  # extract day-of-month
        if c["count"] > 0:
            intensity = min(3, c["count"])  # 1-3 levels
            cls = f"rel-cal rel-lv{intensity}"
        else:
            cls = "rel-cal rel-lv0"
        title = f'{c["date"]}: {c["count"]} release(s)'
        cells += f'<span class="{cls}" title="{title}">{day}</span>'
    return f'<div class="rel-calendar">{cells}</div>'

# ── news ticker (last-hour merges) ─────────────────────────────────────────

def _prefix(title: str) -> tuple[str, str]:
    """Split conventional-commit prefix from description."""
    m = re.match(r'^(\w+(?:\([^)]*\))?:)\s*(.+)', title)
    if m:
        return m.group(1), m.group(2)
    return "", title


# ── mission ledger lower-page renderers ─────────────────────────────────────
# These renderers intentionally keep the locked summary cards above unchanged.

def ticker_html(state: dict) -> str:
    """Last-hour merges render in the Now rail. The ticker strip stays empty."""
    return ""


def _story_ts(value: str) -> float:
    if not value:
        return 0.0
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def news_stories(state: dict) -> list[dict]:
    """Home feed: opened or merged in the last 48 hours. Nothing weeks old."""
    maintainer = state.get("maintainer") or ""
    # Anchor the 48h window on the data time, not wall-clock, so rebuilding
    # the same state.json is byte-identical (idempotent builds).
    now = dt.datetime.fromtimestamp(_story_ts(state.get("generated") or "") or 0, dt.timezone.utc)
    cutoff = now.timestamp() - 48 * 3600
    now_ts = now.timestamp()
    found: dict[tuple, dict] = {}

    def add(kind: str, number, title, url, author, ts: float, ago: str, lane: str | None = None) -> None:
        if not number or ts < cutoff:
            return
        key = ("issue" if kind == "issue" else "pr", int(number))
        row_lane = lane or ("issue" if kind == "issue" else "pr")
        row = {
            "kind": "issue" if kind == "issue" else "pr",
            "lane": row_lane,
            "number": int(number),
            "title": title or "",
            "url": url or "#",
            "author": author or "",
            "ago": ago or "",
            "maintainer": (author or "") == maintainer,
            "ts": ts,
        }
        prev = found.get(key)
        if prev is None or ts >= prev["ts"]:
            if row_lane != "merged" and prev and prev.get("lane") == "merged":
                row["lane"] = "merged"
            found[key] = row

    for item in state.get("fresh") or []:
        if isinstance(item, dict):
            add(item.get("kind") or "pr", item.get("number"), item.get("title"),
                item.get("url"), item.get("author"), _story_ts(item.get("created_at") or ""),
                item.get("ago") or "", item.get("lane"))
    for item in state.get("merged") or []:
        if not isinstance(item, dict):
            continue
        age = item.get("age_min")
        merged_at = item.get("merged_at") or ""
        ts = _story_ts(merged_at) if merged_at else (
            now_ts - age * 60 if isinstance(age, (int, float)) else 0
        )
        add("merged", item.get("number"), item.get("title"), item.get("url"),
            item.get("author"), ts, item.get("ago") or "", "merged")

    stories = sorted(found.values(), key=lambda row: row["ts"], reverse=True)
    return stories[:2500]


def newsletter_html(state: dict) -> str:
    """Hacker News list on the home page. Older threads stay on their own pages."""
    repo = state.get("repo") or "NousResearch/hermes-agent"
    stories = news_stories(state)
    if not stories:
        return ""
    # Only the first rows ship in HTML (fast first paint); app.js fills the
    # rest from /news.json right after load.
    rows = "\n".join(_hn_row(rank, story) for rank, story in enumerate(stories[:NEWS_HTML_ROWS], 1))
    return f'''  <section class="hn" id="news" data-repo="{esc(repo)}" data-total="{len(stories)}" aria-label="New pull requests">
    <div class="hn-head"><h2>New</h2><span>opened or merged in the last 48 hours {fresh_stamp(state, "news")}</span></div>
    <div class="hn-scroll" id="hn-scroll">
{rows}
    </div>
    <div id="hn-discussion" hidden></div>
  </section>'''


def _hn_row(rank: int, story: dict) -> str:
    blue = " is-maintainer" if story.get("maintainer") else ""
    lane = story.get("lane") or story.get("kind") or "pr"
    label = {"merged": "merged", "issue": "issue", "pr": "pull request"}.get(lane, lane)
    meta = " · ".join(part for part in (label, story.get("author") or "", story.get("ago") or "") if part)
    return (
        f'    <article class="hn-row" data-kind="{esc(story.get("kind") or "pr")}" '
        f'data-number="{int(story.get("number") or 0)}" data-url="{esc(story.get("url") or "#")}" '
        f'data-ts="{int(story.get("ts") or 0)}" data-lane="{esc(lane)}" '
        f'data-author="{esc(story.get("author") or "")}">'
        f'<span class="hn-rank">{rank}</span><div class="hn-main">'
        f'<button type="button" class="hn-title{blue}">{esc(clip(story.get("title") or "", 160))}</button>'
        f'<p class="hn-num">#{int(story.get("number") or 0)}</p>'
        f'<p class="hn-meta">{esc(meta)}</p></div></article>'
    )


def issues_panel(state: dict) -> str:
    return ""
    data = state.get("issues") or {}
    if not isinstance(data, dict):
        data = {}
    recent = data.get("recent") or []
    items = recent[:8] if isinstance(recent, list) else []
    if not items:
        return ""
    rows = []
    for item in items:
        if not isinstance(item, dict):
            item = {}
        raw_labels = item.get("labels") or []
        display = [
            label for label in (raw_labels[:3] if isinstance(raw_labels, list) else [])
            if isinstance(label, str) and label
        ]
        labels_html = ""
        main_cls = "iss-main no-labels"
        if display:
            chips = "".join(f'<span class="iss-label">{esc(label)}</span>' for label in display)
            labels_html = f'<span class="iss-labels">{chips}</span>'
            main_cls = "iss-main"
        comments = item.get("comments", 0) or 0
        comment_text = f'{comments} comment{"s" if comments != 1 else ""}' if comments else ""
        rows.append(f'''      <div class="iss-row"><a class="{main_cls}" href="{esc(item.get("url", "#"))}" target="_blank" rel="noopener">
        <span class="iss-num">#{item.get("number", "")}</span><span class="iss-title">{esc(clip(item.get("title", ""), 120))}</span>{labels_html}
        <span class="iss-meta"><span class="iss-author">{esc(item.get("author", ""))}</span><span class="iss-time">{esc(item.get("ago", ""))}</span>{f'<span class="iss-comments">{comment_text}</span>' if comment_text else ''}</span>
      </a></div>''')
    content = "\n".join(rows)
    return f'''    <section class="ledger-section full-width" id="issues"><div class="ledger-heading"><div><span class="ledger-kicker">01 / QUEUE</span><h2><i class="hgi hgi-stroke hgi-alert-02"></i> Issues</h2></div><span class="card-count">{data.get("total_open", 0):,} open · {data.get("total_closed", 0):,} closed</span></div><div class="iss-list">{content}</div></section>'''


def prs_panel(state: dict) -> str:
    return ""
    data = state.get("pull_requests") or {}
    if not isinstance(data, dict):
        data = {}
    recent = data.get("recent") or []
    rows = []
    for item in (recent[:8] if isinstance(recent, list) else []):
        if not isinstance(item, dict):
            item = {}
        review = item.get("review")
        if item.get("draft"):
            status = '<span class="prs-status prs-draft">draft</span>'
        elif review == "APPROVED":
            status = '<span class="prs-status prs-approved">approved</span>'
        elif review == "CHANGES_REQUESTED":
            status = '<span class="prs-status prs-changes">changes</span>'
        elif review == "REVIEW_REQUIRED":
            status = '<span class="prs-status prs-review">review</span>'
        else:
            status = '<span class="prs-status prs-open">open</span>'
        ci_total = item.get("ci_total") or 0
        ci_html = ""
        if ci_total:
            ci = item.get("ci") or "none"
            if ci not in ("passing", "failing", "pending", "none"):
                ci = "none"
            ci_html = f' <span class="prs-ci prs-ci-{ci}">{item.get("ci_ok") or 0}/{ci_total}</span>'
        status = status.replace("</span>", f"{ci_html}</span>", 1)
        rows.append(f'''      <div class="prs-row"><a class="prs-main" href="{esc(item.get("url", "#"))}" target="_blank" rel="noopener">
        <span class="prs-num">#{item.get("number", "")}</span><span class="prs-title">{esc(clip(item.get("title", ""), 120))}</span>{status}<span class="prs-author">{esc(item.get("author", ""))}</span><span class="prs-diff"><span class="add">+{item.get("additions", 0)}</span> <span class="del">-{item.get("deletions", 0)}</span></span><span class="prs-time">{esc(item.get("ago", ""))}</span>
      </a></div>''')
    if not rows:
        return ""
    content = "\n".join(rows)
    return f'''    <section class="ledger-section full-width" id="prs"><div class="ledger-heading"><div><span class="ledger-kicker">02 / REVIEW</span><h2><i class="hgi hgi-stroke hgi-git-pull-request"></i> Pull Requests</h2></div><span class="card-count">{data.get("total_open", 0):,} open · {data.get("total_closed", 0):,} closed</span></div><div class="prs-list">{content}</div></section>'''


def contributors_panel(state: dict) -> str:
    return ""
    blob = state.get("contributors") or {}
    if not isinstance(blob, dict):
        blob = {}
    listed = blob.get("contributors") or []
    contribs = listed[:12] if isinstance(listed, list) else []
    if not contribs:
        return ""
    peak = max((item.get("contributions") or 0) if isinstance(item, dict) else 0 for item in contribs)
    rows = []
    for rank, item in enumerate(contribs, 1):
        if not isinstance(item, dict):
            item = {}
        count = item.get("contributions") or 0
        width = round(100 * count / peak) if peak else 0
        rows.append(f'''      <a class="contrib-row" href="{esc(item.get("html_url", "#"))}" target="_blank" rel="noopener"><span class="contrib-rank">{rank:02d}</span><img class="contrib-avatar" src="{esc(item.get("avatar_url", ""))}&s=64" alt="" loading="lazy" width="28" height="28"><span class="contrib-name">{esc(item.get("login", ""))}</span><span class="contrib-meter" style="--w:{width}%"><span></span></span><span class="contrib-count">{count:,} contributions</span></a>''')
    content = "\n".join(rows)
    return f'''    <section class="ledger-section full-width" id="contributors"><div class="ledger-heading"><div><span class="ledger-kicker">03 / DISPATCHES</span><h2><i class="hgi hgi-stroke hgi-user-group"></i> Contributors</h2></div><span class="ledger-note">ranked by contributions</span></div><div class="contrib-list">{content}</div></section>'''


def quality_panel(state: dict) -> str:
    """Maintainer-program panel: watch ledger, corpus, review lane.

    Everything here comes from the local nous-pr-bot program state that
    fetch_state.quality_program() merged into state.json. Nothing is
    fetched live and nothing here can post to GitHub.
    """
    q = _as_dict(state.get("quality"))
    if not q:
        return ""
    corpus = _as_dict(q.get("corpus"))
    rq = _as_dict(q.get("review_queue"))
    counts = _as_dict(q.get("counts"))
    drafts = _as_list(q.get("drafts"))
    followups = _as_list(q.get("followups"))
    last = _as_dict(q.get("last_removed"))
    repo = state.get("repo") or "NousResearch/hermes-agent"

    def stat(label, value, dim="") -> str:
        return (f'          <div class="stat-row">\n'
                f'            <span class="stat-label">{esc(str(label))}</span>\n'
                f'            <span class="stat-val">{esc(str(value))}</span>\n'
                f'            <span class="stat-dim">{esc(str(dim))}</span>\n'
                f'          </div>')

    # test-discipline split: regression / red-on-main / none / integration
    ratio_raw = str(corpus.get("ratio") or "")
    ratio_parts = [p.strip() for p in ratio_raw.split("/") if p.strip()]
    ratio_names = ["regression-test", "red-on-main-proof", "none", "integration-test"]
    batch = int(corpus.get("batch") or 0)
    bars = ""
    for i, name in enumerate(ratio_names):
        if i >= len(ratio_parts):
            break
        try:
            val = int(re.sub(r"[^0-9]", "", ratio_parts[i]) or 0)
        except ValueError:
            val = 0
        pct = round(val * 100 / batch) if batch else 0
        bars += (f'          <div class="bar-row">\n'
                 f'            <span class="bar-label">{esc(name)}</span>\n'
                 f'            <div class="bar-fill" style="width:{pct}%"></div>\n'
                 f'            <span class="bar-count">{val}</span>\n'
                 f'          </div>\n')

    draft_rows = ""
    for d in drafts[:8]:
        if not isinstance(d, dict):
            continue
        pr = d.get("pr") or ""
        verdict = d.get("verdict") or ""
        score = d.get("score") or ""
        draft_rows += (f'          <div class="stat-row">\n'
                       f'            <a class="stat-val" '
                       f'href="https://github.com/{esc(repo)}/pull/{esc(str(pr))}" '
                       f'target="_blank" rel="noopener">#{esc(str(pr))}</a>\n'
                       f'            <span class="stat-label">{esc(verdict)}</span>\n'
                       f'            <span class="stat-dim">{esc(score) or "unscored"}</span>\n'
                       f'          </div>\n')

    fu_rows = ""
    for f in followups[:6]:
        if not isinstance(f, dict):
            continue
        pr = f.get("pr") or ""
        gap = f.get("gap") or ""
        since = f.get("since") or ""
        fu_rows += (f'          <div class="stat-row">\n'
                    f'            <a class="stat-val" '
                    f'href="https://github.com/{esc(repo)}/pull/{esc(str(pr))}" '
                    f'target="_blank" rel="noopener">#{esc(str(pr))}</a>\n'
                    f'            <span class="stat-dim">{esc(gap)}</span>\n'
                    f'            <span class="stat-label">{esc(since)}</span>\n'
                    f'          </div>\n')

    last_line = ""
    if last.get("pr"):
        last_line = stat(
            "last resolved", f"#{last.get('pr')}",
            f"{last.get('reason', '')} · {last.get('title', '')[:60]}")

    track_note = esc(str(counts.get("watch_definition") or "whole maintainer team"))
    lane_note = esc(str(counts.get("lane_definition") or ""))

    return f'''    <section class="ledger-section full-width" id="quality" aria-label="Maintainer program">
      <div class="ledger-heading">
        <div><span class="ledger-kicker">04 / QUALITY</span>
        <h2><i class="hgi hgi-stroke hgi-verified" aria-hidden="true"></i> Maintainer Program</h2></div>
        <span class="card-count"><span data-api="quality.tracked_open">{q.get("tracked_open", 0)}</span> tracked · <span data-api="quality.removed_total">{q.get("removed_total", 0)}</span> resolved · corpus <span data-api="quality.corpus.live_total">{corpus.get("live_total", 0)}</span> {fresh_stamp(state, "quality", api=True)}</span>
      </div>

      <div class="section-label">lane scope — two definitions, never mixed</div>
{stat("watch", counts.get("watch_tracked", q.get("tracked_open", 0)), track_note)}
{stat("lane", counts.get("lane_open") or state.get("open_in_maintainer_lane") or 0, lane_note)}

      <div class="section-label">program totals</div>
{stat("resolved in ledger", q.get("removed_total", 0), "merged or closed since start")}
{stat("corpus live", corpus.get("live_total", 0), f"curated {corpus.get('curated_total', 0)} · last batch +{corpus.get('batch', 0)}")}
{stat("top bug class", corpus.get("top_bug_class") or "n/a", f"test discipline {corpus.get('regression_pct') or 'n/a'} regression")}
{stat("reviews posted", q.get("posted_reviews", 0), "gate: score >= 8/10 with two-revision proof")}
{last_line}

      <div class="section-label">test discipline — latest batch {esc(ratio_raw) or "n/a"}</div>
{bars}
      <div class="section-label">review drafts — SWE-2 lab</div>
{draft_rows or stat("drafts", q.get("drafts_count", 0), "none on disk")}

      <div class="section-label">open follow-ups</div>
{fu_rows or stat("follow-ups", rq.get("followups", 0), "none")}
    </section>'''


ECO_CATEGORIES = ("plugins", "skills", "mods", "mcp", "tools")


def fresh_stamp(state: dict, panel: str, api: bool = False) -> str:
    """Small per-panel freshness stamp. app.js rewrites it to local time and,
    for API-backed panels, to the live API time when the fetch succeeds."""
    built = str(state.get("generated") or "")
    label = f"snapshot {built[11:16]}Z" if len(built) >= 16 else "snapshot"
    api_attr = ' data-api-panel="1"' if api else ""
    return (f'<span class="fresh-stamp" data-fresh="{esc(panel)}" data-built="{esc(built)}"{api_attr} '
            f'title="Build-time snapshot {esc(built)}">{esc(label)}</span>')


def ecosystem_panel(state: dict) -> str:
    """05 / ECOSYSTEM — dashboard entry point into the faceted explorer view.

    The 1,113-item catalog no longer ships inside index.html; the explorer
    (#ecosystem view, explorer.js) loads per-category shards from data/.
    """
    eco = _as_dict(state.get("catalog"))
    generated = esc(str(eco.get("generated") or ""))
    total = sum(len(_as_list(eco.get(c))) for c in ECO_CATEGORIES)
    links = "\n".join(
        f'        <a class="eco-cat-link" href="#ecosystem?cat={c}"><span class="eco-cat-n" '
        f'data-api="ecosystem.{c}">{len(_as_list(eco.get(c))):,}</span> <span>{c}</span></a>'
        for c in ECO_CATEGORIES)
    return f'''    <section class="ledger-section full-width" id="ecosystem-panel" aria-labelledby="eco-h">
      <div class="ledger-heading">
        <div><span class="ledger-kicker">05 / ECOSYSTEM</span>
        <h2 id="eco-h"><i class="hgi hgi-stroke hgi-grid" aria-hidden="true"></i> Ecosystem explorer</h2></div>
        <span class="card-count">{total:,} free items · catalog {generated[:10]} {fresh_stamp(state, "ecosystem", api=True)}</span>
      </div>
      <div class="eco-cat-grid">
{links}
      </div>
      <p class="eco-note"><a href="#ecosystem">Open the explorer</a> — filter by category and license, sort by stars, and see health flags. Free items only, by policy. Machine mirror: <a href="/ecosystem.json">/ecosystem.json</a></p>
    </section>'''


def prarchive_panel(state: dict) -> str:
    """06 / ARCHIVE — last 1,000 PRs, 100 per page, loaded from data/archive.json."""
    arch = _read_archive()
    total = arch.get("total") or 0
    per = arch.get("per_page") or 100
    generated = esc(str(arch.get("generated") or "")[:10])
    return f'''    <section class="ledger-section full-width" id="prarchive" aria-labelledby="prarch-h" data-per="{int(per)}">
      <div class="ledger-heading">
        <div><span class="ledger-kicker">06 / ARCHIVE</span>
        <h2 id="prarch-h"><i class="hgi hgi-stroke hgi-history" aria-hidden="true"></i> PR Archive</h2></div>
        <span class="card-count">{total:,} PRs · {per}/page · data {generated} {fresh_stamp(state, "archive")}</span>
      </div>
      <div class="eco-controls">
        <label class="sr-only" for="prarch-search">Search archived PRs</label>
        <input id="prarch-search" class="search-input" type="search"
               placeholder="Search archived PRs — number, title, author…">
      </div>
      <div id="prarch-list" class="prs-list" aria-live="polite"><p class="eco-note">Loading the archive…</p></div>
      <div class="eco-pager" id="prarch-pager" role="group" aria-label="Archive pages"></div>
      <p class="eco-note">Most recent {total:,} archived PRs. Click a row for details. Older records: the API with a key — see <a href="#docs">API docs</a>. Mirror: <a href="/prs_archive.json">/prs_archive.json</a></p>
    </section>'''


def _read_archive() -> dict:
    try:
        arch = json.loads((ROOT / "prs_archive.json").read_text(encoding="utf-8"))
        if isinstance(arch, dict):
            return arch
    except Exception:
        pass
    return {"total": 0, "pages": 1, "per_page": 100, "prs": []}


# ── trends: velocity sparklines + retention cohorts (build-time inline SVG) ──

def _week_start(day: dt.date) -> dt.date:
    return day - dt.timedelta(days=day.weekday())


def _parse_day(value) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _search_href(**params) -> str:
    from urllib.parse import quote
    parts = [f"{k}={quote(str(v), safe='')}" for k, v in params.items() if v not in (None, "")]
    return "#search?" + "&".join(parts)


def merge_history(state: dict, previous: dict) -> dict:
    """Accumulate per-day merge counts and backlog snapshots across builds.

    Keyed by data date (never wall-clock), so re-running a build with the
    same state.json produces byte-identical output.
    """
    merges = dict(_as_dict(previous.get("merges")))
    for day, count in _as_dict(_as_dict(state.get("merge_rate")).get("day_counts")).items():
        if _parse_day(day) and isinstance(count, (int, float)):
            merges[str(day)[:10]] = int(count)
    backlog = dict(_as_dict(previous.get("backlog")))
    gen_day = _parse_day(state.get("generated"))
    total_open = _as_dict(state.get("backlog")).get("total_open")
    if gen_day and isinstance(total_open, int):
        backlog[gen_day.isoformat()] = total_open
    return {
        "note": "Accumulated by build.py from state.json on each build: merges/day "
                "(GitHub search, all authors) and backlog total per build day.",
        "merges": dict(sorted(merges.items())),
        "backlog": dict(sorted(backlog.items())),
    }


def archive_merges(state: dict, arch: dict) -> dict[int, tuple[dt.date, str]]:
    """Browsable merged PRs: archive rows + the live blue-strip rows."""
    out: dict[int, tuple[dt.date, str]] = {}
    for row in _as_list(arch.get("prs")):
        if not isinstance(row, dict) or row.get("s") != "merged":
            continue
        day = _parse_day(row.get("m"))
        if day and row.get("n"):
            out[int(row["n"])] = (day, str(row.get("a") or ""))
    for row in _as_list(state.get("merged")):
        if not isinstance(row, dict):
            continue
        day = _parse_day(row.get("merged_at"))
        if day and row.get("number"):
            out[int(row["number"])] = (day, str(row.get("author") or ""))
    return out


def compute_insights(state: dict, history: dict, arch: dict) -> dict:
    gen_day = _parse_day(state.get("generated")) or dt.date(1970, 1, 1)
    browsable = archive_merges(state, arch)
    merges = {_parse_day(k): v for k, v in _as_dict(history.get("merges")).items()}

    # merges/week — last 16 weeks ending with the data week
    last_week = _week_start(gen_day)
    weeks = []
    for i in range(15, -1, -1):
        start = last_week - dt.timedelta(weeks=i)
        days = [start + dt.timedelta(days=d) for d in range(7)]
        elapsed = [d for d in days if d <= gen_day]
        covered = [d for d in elapsed if d in merges]
        merged = sum(merges[d] for d in covered)
        rec = sum(1 for day, _a in browsable.values() if start <= day < start + dt.timedelta(days=7))
        weeks.append({
            "week": start.isoformat(),
            "merged": merged,
            "browsable": rec,
            "days_covered": len(covered),
            "days_elapsed": len(elapsed),
            "in_progress": len(elapsed) < 7,
            "count_gap": len(covered) < len(elapsed),
            "archive_partial": rec < merged,
        })

    # backlog trend — last 30 days of build-day snapshots
    backlog = {_parse_day(k): v for k, v in _as_dict(history.get("backlog")).items()}
    points = []
    for i in range(29, -1, -1):
        day = gen_day - dt.timedelta(days=i)
        points.append({"date": day.isoformat(), "open": backlog.get(day)})

    # retention cohorts from the archive (first merge month within the archive)
    by_author: dict[str, list[dt.date]] = {}
    for day, author in browsable.values():
        if author:
            by_author.setdefault(author, []).append(day)
    cohorts: dict[str, dict] = {}
    for author, days in by_author.items():
        days.sort()
        month = days[0].strftime("%Y-%m")
        c = cohorts.setdefault(month, {"month": month, "firsts": 0, "returned": 0, "authors": []})
        c["firsts"] += 1
        c["authors"].append(author)
        if any(d > days[0] for d in days[1:]):
            c["returned"] += 1
    cohort_rows = []
    for month in sorted(cohorts):
        c = cohorts[month]
        c["authors"].sort(key=str.lower)
        c["share"] = round(c["returned"] / c["firsts"], 3) if c["firsts"] else 0
        cohort_rows.append(c)

    return {
        "generated": state.get("generated") or "",
        "weeks": weeks,
        "backlog": points,
        "cohorts": cohort_rows,
        "cohort_definition": ("Cohort = authors whose first merge in the browsable archive falls in "
                              "that month; returned = merged again on a later day within the archive."),
        "browsable_merges": len(browsable),
    }


def _fmt_week(iso: str) -> str:
    day = _parse_day(iso)
    return f"{day.strftime('%b')} {day.day}" if day else iso


def velocity_svg(ins: dict) -> str:
    weeks = ins["weeks"]
    peak = max([w["merged"] for w in weeks] + [1])
    w, h, pad_b, pad_t = 480, 120, 22, 10
    bw = w / len(weeks)
    gh = h - pad_b - pad_t
    bars = []
    for i, wk in enumerate(weeks):
        x = i * bw + 2
        full = gh * wk["merged"] / peak
        part = gh * min(wk["browsable"], wk["merged"]) / peak if wk["merged"] else 0
        y = pad_t + gh - full
        end = (_parse_day(wk["week"]) + dt.timedelta(days=6)).isoformat()
        href = _search_href(lane="prs", state="merged", **{"from": wk["week"], "to": end})
        notes = []
        if wk["in_progress"]:
            notes.append("week in progress")
        if wk["count_gap"]:
            notes.append(f"counts for {wk['days_covered']} of {wk['days_elapsed']} days")
        if wk["archive_partial"]:
            notes.append(f"{wk['browsable']:,} of {wk['merged']:,} browsable in the archive")
        if not wk["days_covered"]:
            notes = [f"{wk['browsable']:,} browsable in the archive"] if wk["browsable"] else []
            head = f"Week of {_fmt_week(wk['week'])}: no merge counts recorded (gap)"
        else:
            head = f"Week of {_fmt_week(wk['week'])}: {wk['merged']:,} merged"
        label = head + (" — " + "; ".join(notes) if notes else "") + ". Open in search."
        cls = "vb" + (" vb-gap" if wk["count_gap"] or not wk["merged"] else "")
        marker = ""
        if wk["archive_partial"]:
            marker = (f'<rect class="gap-mark" x="{x:.1f}" y="{h - pad_b + 3}" width="{bw - 4:.1f}" '
                      f'height="3"/>')
        if not wk["merged"]:
            y, full = pad_t + gh - 2, 2
        bars.append(
            f'<a href="{esc(href)}" aria-label="{esc(label)}"><title>{esc(label)}</title>'
            f'<rect class="vb-hit" x="{x - 2:.1f}" y="{pad_t}" width="{bw:.1f}" height="{h - pad_t:.1f}"/>'
            f'<rect class="{cls}" x="{x:.1f}" y="{y:.1f}" width="{bw - 4:.1f}" height="{full:.1f}"/>'
            f'<rect class="vb-rec" x="{x:.1f}" y="{pad_t + gh - part:.1f}" width="{bw - 4:.1f}" height="{part:.1f}"/>'
            f'{marker}</a>')
    first, last = weeks[0]["week"], weeks[-1]["week"]
    return (f'<svg class="spark" viewBox="0 0 {w} {h}" role="group" aria-label="Merges per week, '
            f'{esc(_fmt_week(first))} to {esc(_fmt_week(last))}">'
            + "".join(bars)
            + f'<text class="chart-label" x="0" y="{h - 2}">{esc(_fmt_week(first))}</text>'
            + f'<text class="chart-label" x="{w}" y="{h - 2}" text-anchor="end">{esc(_fmt_week(last))}</text>'
            + f'<text class="chart-label" x="0" y="{pad_t - 1}">{peak:,}/wk</text></svg>')


def backlog_svg(ins: dict) -> str:
    pts = ins["backlog"]
    vals = [p["open"] for p in pts if isinstance(p["open"], int)]
    w, h, pad_b, pad_t = 480, 90, 22, 10
    gh = h - pad_b - pad_t
    if not vals:
        return '<p class="eco-note">No backlog snapshots recorded yet.</p>'
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    step = w / (len(pts) - 1 or 1)
    marks, line, seg = [], [], []
    for i, p in enumerate(pts):
        x = i * step
        day = _parse_day(p["date"])
        start = _week_start(day)
        href = _search_href(lane="prs", **{"from": start.isoformat(),
                                           "to": (start + dt.timedelta(days=6)).isoformat()})
        if not isinstance(p["open"], int):
            if seg:
                line.append(seg)
                seg = []
            label = f"{_fmt_week(p['date'])}: no snapshot recorded (gap). Open that week in search."
            marks.append(f'<a href="{esc(href)}" aria-label="{esc(label)}"><title>{esc(label)}</title>'
                         f'<rect class="vb-hit" x="{x - step / 2:.1f}" y="{pad_t}" width="{step:.1f}" height="{h - pad_t:.1f}"/>'
                         f'<rect class="gap-mark" x="{x - 1.5:.1f}" y="{h - pad_b + 3}" width="3" height="3"/></a>')
            continue
        y = pad_t + gh - gh * (p["open"] - lo) / span if hi != lo else pad_t + gh / 2
        seg.append(f"{x:.1f},{y:.1f}")
        label = f"{_fmt_week(p['date'])}: {p['open']:,} open PRs in the backlog panel. Open that week in search."
        marks.append(f'<a href="{esc(href)}" aria-label="{esc(label)}"><title>{esc(label)}</title>'
                     f'<rect class="vb-hit" x="{x - step / 2:.1f}" y="{pad_t}" width="{step:.1f}" height="{h - pad_t:.1f}"/>'
                     f'<circle class="bp" cx="{x:.1f}" cy="{y:.1f}" r="3"/></a>')
    if seg:
        line.append(seg)
    polys = "".join(f'<polyline class="bl" points="{" ".join(s)}"/>' for s in line if len(s) > 1)
    return (f'<svg class="spark" viewBox="-4 0 {w + 8} {h}" role="group" aria-label="Backlog trend, last 30 days">'
            + polys + "".join(marks)
            + f'<text class="chart-label" x="0" y="{h - 2}">{esc(_fmt_week(pts[0]["date"]))}</text>'
            + f'<text class="chart-label" x="{w}" y="{h - 2}" text-anchor="end">{esc(_fmt_week(pts[-1]["date"]))}</text>'
            + f'<text class="chart-label" x="0" y="{pad_t - 1}">{hi:,} max</text></svg>')


def cohort_svg(ins: dict) -> str:
    rows = ins["cohorts"]
    if not rows:
        return '<p class="eco-note">No merged PRs in the archive yet.</p>'
    w, h, pad_b, pad_t = 480, 110, 22, 12
    gh = h - pad_b - pad_t
    bw = min(80, w / len(rows))
    out = []
    for i, c in enumerate(rows):
        x = i * bw + 4
        bar = gh * c["share"]
        href = _search_href(lane="prs", state="merged", cohort=c["month"])
        pct = round(c["share"] * 100)
        label = (f"{c['month']} cohort: {c['returned']} of {c['firsts']} first-time authors "
                 f"merged again ({pct}%). Open the cohort in search.")
        out.append(f'<a href="{esc(href)}" aria-label="{esc(label)}"><title>{esc(label)}</title>'
                   f'<rect class="vb-hit" x="{x - 4:.1f}" y="0" width="{bw:.1f}" height="{h}"/>'
                   f'<rect class="cb-bg" x="{x:.1f}" y="{pad_t}" width="{bw - 8:.1f}" height="{gh}"/>'
                   f'<rect class="cb" x="{x:.1f}" y="{pad_t + gh - bar:.1f}" width="{bw - 8:.1f}" height="{bar:.1f}"/>'
                   f'<text class="chart-label" x="{x + (bw - 8) / 2:.1f}" y="{pad_t + gh - bar - 2:.1f}" text-anchor="middle">{pct}%</text>'
                   f'<text class="chart-label" x="{x + (bw - 8) / 2:.1f}" y="{h - 2}" text-anchor="middle">{esc(c["month"])} · {c["firsts"]}</text></a>')
    return (f'<svg class="spark" viewBox="0 0 {w} {h}" role="group" aria-label="Contributor retention by first-merge month">'
            + "".join(out) + "</svg>")


def trends_panel(state: dict, ins: dict) -> str:
    return f'''    <section class="ledger-section full-width" id="trends" aria-labelledby="trends-h">
      <div class="ledger-heading">
        <div><span class="ledger-kicker">07 / TRENDS</span>
        <h2 id="trends-h"><i class="hgi hgi-stroke hgi-chart-line-data-01" aria-hidden="true"></i> Velocity &amp; retention</h2></div>
        <span class="card-count">{fresh_stamp(state, "trends")}</span>
      </div>
      <div class="trend-grid">
        <figure class="trend">
          <figcaption>Merges per week — all authors</figcaption>
          {velocity_svg(ins)}
          <p class="chart-legend"><span class="lg lg-bar"></span> merged (GitHub search counts) <span class="lg lg-rec"></span> browsable in the archive <span class="lg lg-gap"></span> archive covers only part of that week. Dashed bars: counts missing for some days. Click a bar to search that week.</p>
        </figure>
        <figure class="trend">
          <figcaption>PR backlog — one snapshot per build day</figcaption>
          {backlog_svg(ins)}
          <p class="chart-legend"><span class="lg lg-gap"></span> no snapshot that day. The trend fills in as daily builds accumulate. Click a point to search that week.</p>
        </figure>
        <figure class="trend">
          <figcaption>Contributor retention — share of first-time authors who merged again</figcaption>
          {cohort_svg(ins)}
          <p class="chart-legend">{esc(ins["cohort_definition"])} Later cohorts have had less time to return. Click a bar to search the cohort.</p>
        </figure>
      </div>
    </section>'''


# ── API docs (build-time HTML; curl builder is wired by app.js) ─────────────

API_BASE = "https://nous.minddragonlabs.com/api/v1"
API_ENDPOINTS = [
    # (path, param, summary, public behaviour, keyed behaviour)
    ("/overview", "", "Current counts and lane state: watch/lane counts, quality summary, ecosystem counts.",
     "Full current snapshot.", "Same."),
    ("/prs", "page", "Pull-request records, 100 per page.",
     "Only records from the last 6 hours (often an empty list).", "Full history with X-Nous-Api-Key."),
    ("/prs/{number}", "number", "One pull-request record.",
     "Only when the record is inside the 6-hour window; otherwise an error (observed: 404).",
     "Any archived PR with X-Nous-Api-Key."),
    ("/corpus/stats", "", "Quality-corpus counts (live, curated, last batch, test discipline).",
     "Counts only.", "Labels, fix patterns and lessons with X-Nous-Api-Key."),
    ("/ecosystem/plugins", "", "Free-only ecosystem catalog: plugins.", "Current catalog.", "Same."),
    ("/ecosystem/skills", "", "Free-only ecosystem catalog: skills.", "Current catalog.", "Same."),
    ("/ecosystem/mods", "", "Free-only ecosystem catalog: mods.", "Current catalog.", "Same."),
    ("/ecosystem/mcp", "", "Free-only ecosystem catalog: MCP servers.", "Current catalog.", "Same."),
    ("/ecosystem/tools", "", "Free-only ecosystem catalog: tools.", "Current catalog.", "Same."),
    ("/search", "q", "Search the ecosystem catalog and PR records.",
     "Ecosystem matches + PRs from the last 6 hours (prs_history_truncated: true).",
     "PR history included with X-Nous-Api-Key."),
    ("/usage", "", "Plan, rate limit (60 requests/minute) and monthly call credit.", "Free plan.", "Your key's plan."),
    ("/auth/check", "", "Validate a key. Returns {\"tier\", \"valid\"}.",
     "{\"tier\":\"public\",\"valid\":false}", "{\"valid\":true} for a valid key."),
]


def docs_html() -> str:
    rows = []
    options = []
    for path, param, summary, public, keyed in API_ENDPOINTS:
        rows.append(f'''        <tr><th scope="row"><code>GET {esc(path)}</code></th><td>{esc(summary)}</td><td>{esc(public)}</td><td>{esc(keyed)}</td></tr>''')
        options.append(f'<option value="{esc(path)}" data-param="{esc(param)}">{esc(path)}</option>')
    return f'''  <div class="doc-page" id="api-docs">
    <h2 id="docs-h">API docs</h2>
    <p>Base URL: <code>{API_BASE}</code>. JSON over HTTPS, GET only. The index lives at <a href="https://nous.minddragonlabs.com/api"><code>/api</code></a>.</p>
    <h3>Access tiers</h3>
    <ul class="doc-list">
      <li><strong>Public (no key, free):</strong> current state plus records from the <strong>last 6 hours</strong>. Responses say <code>"tier":"public","public_window_hours":6</code>.</li>
      <li><strong>Historical (key):</strong> send <code>X-Nous-Api-Key: &lt;key&gt;</code> for records older than 6 hours. Keys are issued by the site operator.</li>
      <li><strong>Attribution:</strong> send <code>X-Nous-Attribution: &lt;your app name&gt;</code> on every call. It is required by policy. Every response also carries an <code>X-Nous-Attribution</code> header with the data credit — keep it with the data.</li>
      <li><strong>Limits:</strong> 60 requests/minute; poll at most once a minute. Data refreshes hourly and is edge-cached up to 5 minutes.</li>
      <li><strong>Browsers:</strong> GET responses allow any origin, but CORS preflight (OPTIONS) is not supported. Cross-origin browser code cannot send custom headers, so call from a server or CLI.</li>
    </ul>
    <h3>Endpoints</h3>
    <div class="table-wrap"><table class="doc-table">
      <caption class="sr-only">API v1 endpoints</caption>
      <thead><tr><th scope="col">Endpoint</th><th scope="col">What</th><th scope="col">Public tier</th><th scope="col">With key</th></tr></thead>
      <tbody>
{chr(10).join(rows)}
      </tbody>
    </table></div>
    <h3 id="curl-h">curl builder</h3>
    <form class="curl-builder" id="curl-builder" aria-labelledby="curl-h">
      <label>Endpoint <select id="cb-endpoint">{"".join(options)}</select></label>
      <label id="cb-param-wrap" hidden><span id="cb-param-label">Parameter</span> <input id="cb-param" type="text" autocomplete="off"></label>
      <label>Attribution <input id="cb-attr" type="text" value="my-app" autocomplete="off"></label>
      <label class="cb-check"><input id="cb-key" type="checkbox"> include API key (reads <code>$NOUS_API_KEY</code>)</label>
      <pre class="curl-out" id="cb-out" tabindex="0" aria-live="polite">curl -sS -H 'X-Nous-Attribution: my-app' '{API_BASE}/overview'</pre>
      <button type="button" class="chip" id="cb-copy">Copy</button> <span class="hn-meta" id="cb-copied" role="status"></span>
    </form>
    <p class="eco-note">Errors return JSON: unknown paths give <code>404 {{"error":"not_found"}}</code>. Policy: <a href="/llms.txt">/llms.txt</a> · <a href="/aillm.txt">/aillm.txt</a>.</p>
  </div>'''


# ── provenance (build-time; can not go stale) ───────────────────────────────

SHARD_BUDGET = 350 * 1024


def provenance(state: dict, db_meta: dict, link_summary: dict, sizes: list[tuple[str, int, int]],
               issues_lane: dict) -> dict:
    q = _as_dict(state.get("quality"))
    corpus = _as_dict(q.get("corpus"))
    counts = _as_dict(q.get("counts"))
    eco = _as_dict(state.get("catalog"))
    issues = _as_dict(state.get("issues"))
    eco_counts = {c: len(_as_list(eco.get(c))) for c in ECO_CATEGORIES}
    issue_total = (issues.get("total_open") or 0) + (issues.get("total_closed") or 0)
    return {
        "generated": state.get("generated") or "",
        "datasets": [
            {"name": "Pull requests", "source": "GitHub REST/GraphQL via gh CLI, read-only backfill",
             "coverage": f"{db_meta.get('prs', 0):,} PRs indexed — complete backfill",
             "status": "complete", "indexed_at": db_meta.get("built_at", ""),
             "gaps": "Browsable on this site: the 1,000-PR archive plus live lists. Full records "
                     "older than 6 hours require an API key."},
            {"name": "Issues", "source": "GitHub via gh CLI, read-only backfill",
             "coverage": f"{issues_lane.get('indexed', 0):,} of {issue_total:,} issues indexed — backfill in progress",
             "status": "partial", "indexed_at": db_meta.get("built_at", ""),
             "gaps": "Older issues not yet backfilled; the 100 most recently updated open issues are always live."},
            {"name": "Ecosystem catalog", "source": "plugin-catalog, optional-skills and GitHub topic search",
             "coverage": f"{sum(eco_counts.values()):,} items — " + ", ".join(f"{v:,} {k}" for k, v in eco_counts.items()),
             "status": "complete (free-only)", "indexed_at": eco.get("generated") or "",
             "gaps": "Free items only, by policy; paid offerings are not listed. Link health: "
                     + (f"{link_summary.get('checked', 0):,} checked, {link_summary.get('dead', 0):,} dead, "
                        f"{link_summary.get('unknown', 0):,} unknown"
                        if link_summary.get("checked") else "not checked yet") + "."},
            {"name": "Quality corpus", "source": "Maintainer quality program (local)",
             "coverage": f"{corpus.get('live_total', 0):,} entries live · {corpus.get('curated_total', 0):,} curated",
             "status": "counts public", "indexed_at": q.get("generated") or "",
             "gaps": "Only counts and document titles are public; content requires an API key."},
            {"name": "Watch lane", "source": "nous-pr-bot watch ledger (read-only)",
             "coverage": f"{counts.get('watch_tracked', q.get('tracked_open', 0)):,} open PRs tracked · "
                         f"{q.get('removed_total', 0):,} resolved",
             "status": "read-only", "indexed_at": q.get("generated") or "",
             "gaps": "Never comments, reviews or reacts on GitHub. Scope: " + str(counts.get("watch_definition") or "")},
            {"name": "Live dashboard state", "source": "fetch_state.py (gh CLI)",
             "coverage": "strips, backlog, releases, merge rate, recent issues/PRs, contributors",
             "status": "snapshot", "indexed_at": state.get("generated") or "",
             "gaps": "Panels backed by /api/v1/overview update in the browser when the API is newer."},
        ],
        "budget": {"per_shard_bytes": SHARD_BUDGET,
                   "rule": "Each JSON shard loaded by the page should stay under 350 KB raw. "
                           "scripts/perf_gate.py prints the table at the end of every build and warns "
                           "(never fails) when a shard is over budget."},
        "shards": [{"path": p, "bytes": raw, "gzip": gz} for p, raw, gz in sizes],
    }


def provenance_html(prov: dict) -> str:
    rows = "\n".join(
        f'''        <tr><th scope="row">{esc(d["name"])}</th><td>{esc(d["coverage"])}</td><td><span class="badge badge-{esc(d["status"].split()[0])}">{esc(d["status"])}</span></td><td>{esc(d["source"])}</td><td>{esc(d["gaps"])}</td><td>{esc(str(d["indexed_at"])[:16].replace("T", " "))}</td></tr>'''
        for d in prov["datasets"])
    shards = "\n".join(
        f'        <tr><th scope="row"><a href="/{esc(s["path"])}">{esc(s["path"])}</a></th><td>{s["bytes"] / 1024:,.1f} KB</td><td>{s["gzip"] / 1024:,.1f} KB</td><td>{"over budget" if s["bytes"] > prov["budget"]["per_shard_bytes"] else "ok"}</td></tr>'
        for s in prov["shards"])
    return f'''  <section class="doc-page" id="provenance" aria-labelledby="prov-h">
    <h2 id="prov-h">Provenance &amp; coverage</h2>
    <p class="tab-note">Generated by build.py from build metadata on {esc(str(prov["generated"]))}. Machine copy: <a href="/data/provenance.json">/data/provenance.json</a>.</p>
    <div class="table-wrap"><table class="doc-table">
      <caption class="sr-only">Datasets, coverage and gaps</caption>
      <thead><tr><th scope="col">Dataset</th><th scope="col">Coverage</th><th scope="col">Status</th><th scope="col">Source</th><th scope="col">Gaps</th><th scope="col">As of (UTC)</th></tr></thead>
      <tbody>
{rows}
      </tbody>
    </table></div>
    <h3>Payload budget</h3>
    <p>{esc(prov["budget"]["rule"])}</p>
    <div class="table-wrap"><table class="doc-table">
      <caption class="sr-only">Data shard sizes</caption>
      <thead><tr><th scope="col">Shard</th><th scope="col">Raw</th><th scope="col">Gzip</th><th scope="col">Budget</th></tr></thead>
      <tbody>
{shards}
      </tbody>
    </table></div>
    <h3>Feeds</h3>
    <p>Notable merges (latest 20, item id = PR number): <a href="/feed.json">/feed.json</a> (JSON Feed) · <a href="/feed.xml">/feed.xml</a> (Atom).</p>
  </section>'''


# ── feed (JSON Feed 1.1 + Atom) ─────────────────────────────────────────────

SITE = "https://nous.minddragonlabs.com"


def feed_items(state: dict, arch: dict, limit: int = 20) -> list[dict]:
    repo = state.get("repo") or "NousResearch/hermes-agent"
    rows: dict[int, dict] = {}
    for row in _as_list(arch.get("prs")):
        if isinstance(row, dict) and row.get("s") == "merged" and _parse_day(row.get("m")):
            n = int(row["n"])
            rows[n] = {"number": n, "title": display_title(row.get("t") or ""), "author": row.get("a") or "",
                       "date": f"{str(row['m'])[:10]}T00:00:00Z", "summary": ""}
    for row in _as_list(state.get("merged")):
        if isinstance(row, dict) and row.get("number") and row.get("merged_at"):
            n = int(row["number"])
            rows[n] = {"number": n, "title": display_title(row.get("title") or ""),
                       "author": row.get("author") or "", "date": row["merged_at"],
                       "summary": str(row.get("summary") or "")}
    items = sorted(rows.values(), key=lambda r: (r["date"], r["number"]), reverse=True)[:limit]
    for it in items:
        it["url"] = f"https://github.com/{repo}/pull/{it['number']}"
    return items


def feed_json(items: list[dict]) -> str:
    return json.dumps({
        "version": "https://jsonfeed.org/version/1.1",
        "title": "Nous Space — notable merges",
        "home_page_url": SITE + "/",
        "feed_url": SITE + "/feed.json",
        "description": "Latest merged pull requests in NousResearch/hermes-agent, from the Nous Space archive. "
                       "Community observation, not official Nous Research statements.",
        "language": "en",
        "items": [{
            "id": str(it["number"]),
            "url": it["url"],
            "title": f"#{it['number']} {it['title']}",
            "content_text": it["summary"] or it["title"],
            "date_published": it["date"],
            "authors": [{"name": it["author"], "url": f"https://github.com/{it['author']}"}] if it["author"] else [],
        } for it in items],
    }, indent=1, ensure_ascii=False) + "\n"


def feed_atom(items: list[dict]) -> str:
    from xml.sax.saxutils import escape as xesc
    updated = items[0]["date"] if items else "1970-01-01T00:00:00Z"
    entries = []
    for it in items:
        author = f"<author><name>{xesc(it['author'])}</name></author>" if it["author"] else ""
        entries.append(
            f"  <entry>\n    <id>urn:nous-space:pr:{it['number']}</id>\n"
            f"    <title>{xesc('#' + str(it['number']) + ' ' + it['title'])}</title>\n"
            f"    <link rel=\"alternate\" href=\"{xesc(it['url'])}\"/>\n"
            f"    <updated>{xesc(it['date'])}</updated>\n    {author}\n"
            f"    <summary>{xesc(it['summary'] or it['title'])}</summary>\n  </entry>")
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<feed xmlns="http://www.w3.org/2005/Atom">\n'
            '  <id>urn:nous-space:feed:merges</id>\n'
            '  <title>Nous Space — notable merges</title>\n'
            f'  <link rel="self" href="{SITE}/feed.xml"/>\n'
            f'  <link rel="alternate" href="{SITE}/"/>\n'
            f'  <updated>{updated}</updated>\n'
            '  <author><name>Nous Space</name></author>\n'
            + "\n".join(entries) + "\n</feed>\n")


# ── data shards ─────────────────────────────────────────────────────────────

def _db_meta_and_issues() -> tuple[dict, list | None]:
    """Read counts + the issues lane from nous-index.db (local, optional)."""
    db_path = ROOT / "nous-index.db"
    if not db_path.exists():
        return {}, None
    import sqlite3
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        meta = dict(con.execute("SELECT k, v FROM meta").fetchall())
        counts = json.loads(meta.get("counts") or "{}")
        counts["built_at"] = meta.get("built_at") or ""
        rows = con.execute("SELECT number, title, author, labels, state FROM issues").fetchall()
        counts["doc_names"] = sorted(str(r[0]) for r in con.execute("SELECT name FROM docs").fetchall())
        con.close()
    except Exception as exc:  # never fail the build on the optional index
        print(f"note: nous-index.db unreadable ({exc}); keeping previous lanes")
        return {}, None
    issues = []
    for number, title, author, labels, st in rows:
        try:
            n = int(number)
        except (TypeError, ValueError):
            continue
        issues.append([n, " ".join(str(title or "").split())[:200], str(author or ""),
                       "o" if str(st).lower() == "open" else "c",
                       [x for x in str(labels or "").split(",") if x][:6]])
    issues.sort(key=lambda r: -r[0])
    return counts, issues


def eco_shard(state: dict, cat: str, links: dict) -> dict:
    eco = _as_dict(state.get("catalog"))
    items = []
    for it in _as_list(eco.get(cat)):
        if not isinstance(it, dict):
            continue
        url = it.get("url") or it.get("repo") or it.get("github_url") or it.get("docs_url") or ""
        desc = " ".join(str(it.get("description") or "").split())
        stars = it.get("stars") if isinstance(it.get("stars"), int) else None
        src = it.get("source") or ("catalog" if it.get("tier") or it.get("sha") else
                                   "optional-skills" if it.get("slug") else "")
        flags = []
        if it.get("archived") is True:
            flags.append("archived")
        if not desc:
            flags.append("no-description")
        if src == "github" and stars == 0:
            flags.append("no-stars")
        link = _as_dict(links.get(url)).get("status") if url else None
        if link == "dead":
            flags.append("dead-link")
        sub = str(it.get("category") or "")
        items.append({
            "n": str(it.get("name") or it.get("slug") or ""),
            "u": url,
            "d": desc[:280] + ("…" if len(desc) > 280 else ""),
            "s": stars,
            "l": str(it.get("license") or ("" if src == "github" else "catalog")),
            "f": it.get("free") is True,
            "src": src,
            "sub": sub if sub != cat else "",
            "t": str(it.get("tier") or ""),
            "m": str(it.get("maintainer") or ""),
            "fl": flags,
            "lk": link or "",
        })
    return {"category": cat, "generated": eco.get("generated") or "", "total": len(items), "items": items}


def catalog_payload(state: dict) -> dict:
    data = appdata_catalog(state)
    data["lane_open"] = _as_list(state.get("lane_open"))
    data["lane_stale"] = _as_dict(state.get("lane_stale"))
    data["pending"] = _as_list(state.get("pending"))
    data["merged"] = [{k: v for k, v in row.items() if k not in ("body", "images")}
                      for row in _as_list(state.get("merged")) if isinstance(row, dict)]
    return data


def snapshot_island(state: dict, version: str) -> dict:
    """TINY embedded fallback: counts + top rows only. Full lists live in data/."""
    cat = appdata_catalog(state)
    for key in ("issues", "pull_requests"):
        cat[key] = dict(cat[key], items=cat[key]["items"][:10], partial=True)
    cat["contributors"] = {"items": cat["contributors"]["items"][:10], "partial": True}
    cat["ecosystem"] = []
    eco = _as_dict(state.get("catalog"))
    cat["eco_counts"] = {c: len(_as_list(eco.get(c))) for c in ECO_CATEGORIES}
    cat["v"] = version
    cat["api"] = {"base": API_BASE, "window_hours": 6}
    return cat


def _as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value) -> list:
    return list(value) if isinstance(value, list) else []


def appdata_catalog(state: dict) -> dict:
    """Full working set for the client. Item dicts keep their original keys."""
    state = _as_dict(state)
    issues = _as_dict(state.get("issues"))
    pull_requests = _as_dict(state.get("pull_requests"))
    contributors = _as_dict(state.get("contributors"))
    repo = state.get("repo") or ""
    if not isinstance(repo, str):
        repo = ""
    return {
        "generated": state.get("generated"),
        "repo": state.get("repo"),
        "repo_url": "https://github.com/" + repo,
        "branch": state.get("branch"),
        "maintainer": state.get("maintainer"),
        "issues": {
            "total_open": issues.get("total_open"),
            "total_closed": issues.get("total_closed"),
            "scanned": issues.get("scanned"),
            "items": _as_list(issues.get("recent")),
        },
        "pull_requests": {
            "total_open": pull_requests.get("total_open"),
            "total_closed": pull_requests.get("total_closed"),
            "scanned": pull_requests.get("scanned"),
            "items": _as_list(pull_requests.get("recent")),
        },
        "contributors": {
            "items": _as_list(contributors.get("contributors")),
        },
        "ecosystem": _as_list(state.get("ecosystem")),
    }


def appdata_html(state: dict, version: str = "") -> str:
    raw = json.dumps(snapshot_island(state, version), separators=(",", ":")).replace("<", r"\u003c")
    return f'<script id="nous-data" type="application/json">{raw}</script>'


def render_panels(state: dict) -> str:
    return f'''  <div class="dash-row">
{backlog_panel(state)}
{releases_panel(state)}
{merge_rate_panel(state)}
  </div>
  <div class="dash-deck">
  <!-- TICKER:START -->
  <!-- TICKER:END -->
  <!-- NEWSLETTER:START -->
  <!-- NEWSLETTER:END -->
  <!-- ISSUES:START -->
  <!-- ISSUES:END -->
  <!-- PRS:START -->
  <!-- PRS:END -->
  <!-- CONTRIBUTORS:START -->
  <!-- CONTRIBUTORS:END -->
  <!-- PRARCHIVE:START -->
  <!-- PRARCHIVE:END -->
  <!-- ECOSYSTEM:START -->
  <!-- ECOSYSTEM:END -->
  <!-- TRENDS:START -->
  <!-- TRENDS:END -->
  <!-- QUALITY:START -->
  <!-- QUALITY:END -->
  </div>'''


# ── main ────────────────────────────────────────────────────────────────────

TRENDS_START = "<!-- TRENDS:START -->"
TRENDS_END = "<!-- TRENDS:END -->"
DOCS_START = "<!-- DOCS:START -->"
DOCS_END = "<!-- DOCS:END -->"
PROV_START = "<!-- PROVENANCE:START -->"
PROV_END = "<!-- PROVENANCE:END -->"
DATA_DIR = ROOT / "data"


def _dump(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def write_if_changed(path: pathlib.Path, text: str, changed: list[str]) -> None:
    """Atomic write, skipped when the bytes are identical (idempotent builds)."""
    try:
        if path.read_text(encoding="utf-8") == text:
            return
    except (FileNotFoundError, UnicodeDecodeError):
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    changed.append(str(path.relative_to(ROOT)))


def _read_json(path: pathlib.Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def _fill(page: str, start: str, end: str, body: str, required: bool = False) -> str:
    if start not in page or end not in page:
        if required:
            raise SystemExit(f"ERROR: marker {start} missing from index.html")
        return page
    i = page.index(start) + len(start)
    j = page.find(end, i)
    if j == -1:
        return page
    return page[:i] + "\n" + body + "\n  " + page[j:]


def _perf_gate():
    import importlib.util
    spec = importlib.util.spec_from_file_location("perf_gate", ROOT / "scripts" / "perf_gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_data(state: dict, changed: list[str]) -> dict:
    """Emit data/*.json shards. Returns what the HTML render needs."""
    if os.environ.get("NOUS_LINK_CHECK") == "1":
        # opt-in: refresh the 72h link cache first. Flag-only, never fails the build.
        try:
            subprocess.run([sys.executable, str(ROOT / "scripts" / "link_check.py"), "--max", "150"],
                           timeout=150, check=False)
        except Exception as exc:  # noqa: BLE001
            print(f"note: link check skipped ({exc})")
    arch = _read_archive()
    db_meta, db_issues = _db_meta_and_issues()
    links =_as_dict(_read_json(ROOT / "link_check.json", {}).get("results"))
    issues_state = _as_dict(state.get("issues"))
    issue_total = (issues_state.get("total_open") or 0) + (issues_state.get("total_closed") or 0)

    # db-derived values fall back to the previous build when the local index is absent
    prev_prov = _read_json(DATA_DIR / "provenance.json", {})
    if not db_meta:
        db_meta = _as_dict(prev_prov.get("db_meta"))

    history = merge_history(state, _read_json(DATA_DIR / "history.json", {}))
    insights = compute_insights(state, history, arch)
    shards: dict[str, str] = {
        "data/history.json": _dump(history),
        "data/insights.json": _dump(insights),
        "data/catalog.json": _dump(catalog_payload(state)).replace("<", "\\u003c"),
        "data/archive.json": _dump(arch),
    }
    for cat in ECO_CATEGORIES:
        shards[f"data/eco-{cat}.json"] = _dump(eco_shard(state, cat, links))

    if db_issues is not None:
        issues_lane = {"generated": db_meta.get("built_at", ""), "indexed": len(db_issues),
                       "total": issue_total, "complete": False,
                       "note": "Issues backfill in progress; titles, labels and state only.",
                       "items": db_issues}
    else:
        issues_lane = _read_json(DATA_DIR / "search-issues.json",
                                 {"indexed": 0, "total": issue_total, "complete": False, "items": []})
        issues_lane["total"] = issue_total
    shards["data/search-issues.json"] = _dump(issues_lane)

    q = _as_dict(state.get("quality"))
    corpus = _as_dict(q.get("corpus"))
    shards["data/corpus.json"] = _dump({
        "generated": q.get("generated") or "",
        "live_total": corpus.get("live_total", 0),
        "curated_total": corpus.get("curated_total", 0),
        "last_batch": corpus.get("batch", 0),
        "docs": db_meta.get("doc_names") or ["CHARTER.md", "RUBRIC.md", "corpus-trends.md"],
        "public": "titles and counts only",
        "note": "Corpus content (labels, fix patterns, lessons) requires an API key.",
    })

    results = list(links.values())
    link_summary = {
        "checked": len(results),
        "dead": sum(1 for r in results if _as_dict(r).get("status") == "dead"),
        "unknown": sum(1 for r in results if _as_dict(r).get("status") == "unknown"),
    }

    for rel, text in shards.items():
        write_if_changed(ROOT / rel, text, changed)

    gate = _perf_gate()
    sizes = [gate.measure(ROOT / rel) for rel in sorted(shards)]
    sizes = [(rel, raw, gz) for rel, (raw, gz) in zip(sorted(shards), sizes)]
    prov = provenance(state, db_meta, link_summary, sizes, issues_lane)
    prov["db_meta"] = {k: v for k, v in db_meta.items() if k != "doc_names"}
    write_if_changed(DATA_DIR / "provenance.json", _dump(prov), changed)

    import hashlib
    digest = hashlib.sha256("".join(shards[k] for k in sorted(shards)).encode()).hexdigest()[:12]

    items = feed_items(state, arch)
    write_if_changed(ROOT / "feed.json", feed_json(items), changed)
    write_if_changed(ROOT / "feed.xml", feed_atom(items), changed)
    return {"insights": insights, "prov": prov, "version": digest}


def main() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    original = INDEX.read_text(encoding="utf-8")
    page = original
    changed: list[str] = []

    # Remove stale newsletter/ticker bodies that used to live after PANELS.
    # The current render places both sections inside the lower deck.
    page = re.sub(
        re.escape(PANELS_END) + r".*?" + re.escape(TICKER_END),
        PANELS_END,
        page,
        count=1,
        flags=re.S,
    )

    # Remove prior generated section bodies before rebuilding. This keeps
    # repeated refreshes idempotent, even after an interrupted build.
    for start, end in ((ISSUES_START, ISSUES_END),
                       (PRS_START, PRS_END),
                       (CONTRIBUTORS_START, CONTRIBUTORS_END),
                       (PRARCHIVE_START, PRARCHIVE_END),
                       (ECOSYSTEM_START, ECOSYSTEM_END),
                       (TRENDS_START, TRENDS_END),
                       (QUALITY_START, QUALITY_END)):
        page = re.sub(re.escape(start) + r".*?" + re.escape(end),
                      start + end, page, flags=re.S)

    for marker in (START, END, PANELS_START, PANELS_END, CSS_START, CSS_END):
        if marker not in page:
            raise SystemExit(f"ERROR: marker {marker} missing from index.html")

    built = build_data(state, changed)

    # re-inline row.css
    ci = page.index(CSS_START) + len(CSS_START)
    cj = page.index(CSS_END)
    page = page[:ci] + "\n" + (ROOT / "row.css").read_text(encoding="utf-8") + page[cj:]

    page = _fill(page, START, END, render_row(state), required=True)
    page = _fill(page, PANELS_START, PANELS_END, render_panels(state), required=True)
    page = _fill(page, NEWSLETTER_START, NEWSLETTER_END, newsletter_html(state), required=True)
    page = _fill(page, TICKER_START, TICKER_END, ticker_html(state), required=True)
    page = _fill(page, ISSUES_START, ISSUES_END, issues_panel(state), required=True)
    page = _fill(page, PRS_START, PRS_END, prs_panel(state), required=True)
    page = _fill(page, CONTRIBUTORS_START, CONTRIBUTORS_END, contributors_panel(state), required=True)
    page = _fill(page, QUALITY_START, QUALITY_END, quality_panel(state))
    page = _fill(page, ECOSYSTEM_START, ECOSYSTEM_END, ecosystem_panel(state))
    page = _fill(page, PRARCHIVE_START, PRARCHIVE_END, prarchive_panel(state))
    page = _fill(page, TRENDS_START, TRENDS_END, trends_panel(state, built["insights"]))
    page = _fill(page, DOCS_START, DOCS_END, docs_html())
    page = _fill(page, PROV_START, PROV_END, provenance_html(built["prov"]))
    page = _fill(page, APPDATA_START, APPDATA_END, appdata_html(state, built["version"]))

    # JSON mirrors for agents: /ecosystem.json (+ /quality.json) — the
    # machine-readable twins of the HTML views (dual-browsing, PLAN.md item 3)
    write_if_changed(ROOT / "ecosystem.json", _dump_ascii(state.get("catalog") or {}), changed)
    write_if_changed(ROOT / "quality.json", _dump_ascii(state.get("quality") or {}), changed)
    stories = news_stories(state)
    news_meta = {
        "generated": state.get("generated") or "",
        "repo": state.get("repo") or "NousResearch/hermes-agent",
        "maintainer": state.get("maintainer") or "",
    }
    write_if_changed(ROOT / "news.json", _dump_ascii(dict(news_meta, items=stories)), changed)
    # small head shard for the 45s poll; the full 48h wire loads on scroll
    write_if_changed(DATA_DIR / "news-head.json",
                     _dump_ascii(dict(news_meta, total=len(stories), items=stories[:NEWS_HEAD_ROWS])), changed)

    if page != original:
        write_if_changed(INDEX, page, changed)

    gate = _perf_gate()
    gate.report(ROOT)

    if not changed:
        print("build: unchanged — index.html and all data artifacts identical (idempotent)")
        return 0
    pend = ", ".join(f"#{p['number']}" for p in state["pending"][:N_PER_SIDE])
    merg = ", ".join(f"#{x['number']}" for x in state["merged"][:N_PER_SIDE])
    print(f"build: wrote {len(changed)} file(s): {', '.join(changed)}")
    print(f"index.html — green: {pend} | blue: {merg}")
    return 0


def _dump_ascii(obj) -> str:
    # matches the historical mirror format (json.dumps default ASCII escapes)
    return json.dumps(obj, separators=(",", ":"))


if __name__ == "__main__":
    raise SystemExit(main())