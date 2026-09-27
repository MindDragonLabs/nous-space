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
import pathlib
import re

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
QUALITY_START = "<!-- QUALITY:START -->"
QUALITY_END = "<!-- QUALITY:END -->"
APPDATA_START = "<!-- APPDATA:START -->"
APPDATA_END = "<!-- APPDATA:END -->"
CSS_START = "/* ROWCSS:START */"
CSS_END = "/* ROWCSS:END */"
N_PER_SIDE = 5
N_MERGED_SHOW = 30  # enough blocks to overflow any viewport width
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
    return f"""  <div class="stripscroll" id="blockstrip">
    <div class="strip">
      {greens}
      <div class="split"></div>
      {blues}
    </div>
  </div>
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

    def lane_row(label: str, value, dim: str) -> str:
        return (f'        <div class="stat-row">\n'
                f'          <span class="stat-label">{esc(label)}</span>\n'
                f'          <span class="stat-val">{value:,}</span>\n'
                f'          <span class="stat-dim">{esc(dim)}</span>\n'
                f'        </div>')

    lane_html = "\n".join([
        lane_row("watch", watch_tracked, "whole maintainer team"),
        lane_row("lane", lane_open, f"involving {maintainer}"),
    ])

    # ── line chart: new PRs per day over last 7 days ──
    daily = bl.get("daily_new", [])
    chart_svg = _daily_line_chart(daily) if daily else ""

    return f"""    <div class="dash-card left">
      <h3><i class="hgi hgi-stroke hgi-inbox"></i> PR Backlog</h3>
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

    return f"""<svg class="line-chart" viewBox="0 0 {w} {h}" width="{w}" height="{h}">
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
      <h3><i class="hgi hgi-stroke hgi-activity-01"></i> PR Velocity</h3>
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
      <h3><i class="hgi hgi-stroke hgi-rocket-01"></i> Release Velocity</h3>
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
    now = dt.datetime.now(dt.timezone.utc)
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
    rows = "\n".join(_hn_row(rank, story) for rank, story in enumerate(stories, 1))
    return f'''  <section class="hn" id="news" data-repo="{esc(repo)}" aria-label="New pull requests">
    <div class="hn-head"><h2>New</h2><span>opened or merged in the last 48 hours</span></div>
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

    return f'''    <section class="ledger-section full-width" id="quality">
      <div class="ledger-heading">
        <div><span class="ledger-kicker">04 / QUALITY</span>
        <h2><i class="hgi hgi-stroke hgi-verified"></i> Maintainer Program</h2></div>
        <span class="card-count">{q.get("tracked_open", 0)} tracked · {q.get("removed_total", 0)} resolved · corpus {corpus.get("live_total", 0)}</span>
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


def appdata_html(state: dict) -> str:
    raw = json.dumps(appdata_catalog(state), separators=(",", ":")).replace("<", r"\u003c")
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
  <!-- QUALITY:START -->
  <!-- QUALITY:END -->
  </div>'''


# ── main ────────────────────────────────────────────────────────────────────

def main() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    page = INDEX.read_text(encoding="utf-8")

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
                       (QUALITY_START, QUALITY_END)):
        page = re.sub(re.escape(start) + r".*?" + re.escape(end),
                      start + end, page, flags=re.S)

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

    # newsletter
    ni = page.index(NEWSLETTER_START) + len(NEWSLETTER_START)
    nj = page.index(NEWSLETTER_END)
    page = page[:ni] + "\n" + newsletter_html(state) + "\n  " + page[nj:]

    # news ticker
    ti = page.index(TICKER_START) + len(TICKER_START)
    tj = page.index(TICKER_END)
    page = page[:ti] + "\n" + ticker_html(state) + "\n  " + page[tj:]

    # issues
    ii = page.index(ISSUES_START) + len(ISSUES_START)
    ij = page.index(ISSUES_END)
    page = page[:ii] + "\n" + issues_panel(state) + "\n  " + page[ij:]

    # PRs
    pi = page.index(PRS_START) + len(PRS_START)
    pj = page.index(PRS_END)
    page = page[:pi] + "\n" + prs_panel(state) + "\n  " + page[pj:]

    # contributors
    cti = page.index(CONTRIBUTORS_START) + len(CONTRIBUTORS_START)
    ctj = page.index(CONTRIBUTORS_END)
    page = page[:cti] + "\n" + contributors_panel(state) + "\n  " + page[ctj:]

    # quality program (markers optional so a hand-trimmed page still builds)
    if QUALITY_START in page and QUALITY_END in page:
        qi = page.index(QUALITY_START) + len(QUALITY_START)
        qj = page.find(QUALITY_END, qi)
        if qj != -1:
            page = page[:qi] + "\n" + quality_panel(state) + "\n  " + page[qj:]

    # client catalog; markers are optional until index.html includes them
    if APPDATA_START in page and APPDATA_END in page:
        ai = page.index(APPDATA_START) + len(APPDATA_START)
        aj = page.find(APPDATA_END, ai)
        if aj != -1:
            page = page[:ai] + "\n" + appdata_html(state) + "\n  " + page[aj:]

    news_path = ROOT / "news.json"
    news_tmp = news_path.with_suffix(".json.tmp")
    news_tmp.write_text(json.dumps({
        "generated": state.get("generated") or "",
        "repo": state.get("repo") or "NousResearch/hermes-agent",
        "maintainer": state.get("maintainer") or "",
        "items": news_stories(state),
    }, separators=(",", ":")), encoding="utf-8")
    news_tmp.replace(news_path)

    if page == INDEX.read_text(encoding="utf-8"):
        print("index.html unchanged")
        return 0

    index_tmp = INDEX.with_suffix(".html.tmp")
    index_tmp.write_text(page, encoding="utf-8")
    index_tmp.replace(INDEX)
    pend = ", ".join(f"#{p['number']}" for p in state["pending"][:N_PER_SIDE])
    merg = ", ".join(f"#{x['number']}" for x in state["merged"][:N_PER_SIDE])
    print(f"index.html rendered — green: {pend} | blue: {merg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())