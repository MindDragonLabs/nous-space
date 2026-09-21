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

    # ── line chart: new PRs per day over last 7 days ──
    daily = bl.get("daily_new", [])
    chart_svg = _daily_line_chart(daily) if daily else ""

    return f"""    <div class="dash-card left">
      <h3><i class="hgi hgi-stroke hgi-inbox"></i> PR Backlog</h3>
      <div class="big-num">{total:,}</div>
      <div class="big-sub">open pull requests</div>
      {newest_html}
      {oldest_html}
      <div class="section-label">new PRs — last 7 days</div>
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


def merge_rate_panel(state: dict) -> str:
    mr = state.get("merge_rate", {})
    rows = ""
    for period in ["7d", "30d", "90d"]:
        if period in mr:
            r = mr[period]
            rows += f"""        <div class="stat-row">
          <span class="stat-label">{period}</span>
          <span class="stat-val">{r['per_day']} PR/day</span>
          <span class="stat-dim">{r['count']} merged</span>
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

    cadence_html = f"""        <div class="stat-row">
          <span class="stat-label">cadence</span>
          <span class="stat-val">~{cadence}d</span>
          <span class="stat-dim">3 releases in 2 weeks</span>
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


def ticker_html(state: dict) -> str:
    """Generate a marquee ticker of merges from the last hour."""
    merged = state.get("merged", [])
    items: list[tuple[int, str, str]] = []  # (age_min, prefix, description)
    for pr in merged:
        age = pr.get("age_min", 999)
        if age <= 60:
            tag, desc = _prefix(pr["title"])
            desc = desc if len(desc) <= 50 else desc[:47] + "..."
            items.append((age, tag, desc))
    items.sort(key=lambda x: x[0])  # newest first

    if not items:
        return ""

    # Duplicate items so the CSS marquee loop is seamless
    cells = ""
    for age, tag, desc in items:
        cells += f'<span class="ticker-item"><span class="t-time">{age}m</span><span class="t-tag">{esc(tag)}</span> {esc(desc)}</span>'
    # repeat for seamless loop
    cells *= 2

    return f"""  <div class="ticker-wrap">
    <div class="ticker">{cells}
    </div>
  </div>"""


# ── newsletter (≤60 min merges as article blocks) ─────────────────────────

def newsletter_html(state: dict) -> str:
    """Render a news-article style section of recent (≤60 min) merged PRs."""
    merged = state.get("merged", [])
    articles = []
    for m in merged:
        if m.get("age_min", 999) > 60:
            continue
        num = m["number"]
        tag, desc = _prefix(m["title"])
        summary = m.get("summary", desc)
        images = m.get("images", [])
        ago = m.get("ago", "")
        author = m.get("author", "")
        url = m.get("url", "")

        # Build image gallery
        img_html = ""
        for img_url in images[:3]:  # cap at 3 images per article
            img_html += f'<img src="{esc(img_url)}" alt="" class="nw-img" loading="lazy">'
        if img_html:
            img_html = f'<div class="nw-gallery">{img_html}</div>'

        article = f"""  <article class="nw-card">
    <div class="nw-header">
      <a class="nw-link" href="{esc(url)}" target="_blank" rel="noopener">#{num}</a>
      <span class="nw-tag">{esc(tag)}</span>
      <span class="nw-time">{esc(ago)}</span>
    </div>
    <div class="nw-body">
      <p class="nw-summary">{esc(summary)}</p>
      {img_html}
    </div>
    <div class="nw-footer">
      <span class="nw-author">by <a href="https://github.com/{esc(author)}" target="_blank" rel="noopener">{esc(author)}</a></span>
    </div>
  </article>"""
        articles.append(article)

    if not articles:
        return ""

    # Build a horizontal scroll row (like the blockstrip)
    cards = "\n".join(articles)
    return f"""  <section class="newsletter">
    <h2 class="nw-title"><i class="hgi hgi-stroke hgi-news"></i> Latest Merges — Last Hour</h2>
    <div class="nw-strip">
{cards}
    </div>
  </section>"""


def issues_panel(state: dict) -> str:
    """Render a full-width issues list card."""
    is_data = state.get("issues", {})
    items = is_data.get("recent", [])
    total_open = is_data.get("total_open", 0)
    total_closed = is_data.get("total_closed", 0)

    if not items:
        return ""

    rows = ""
    for i in items:
        labels_html = "".join(
            f'<span class="iss-label">{esc(l)}</span>'
            for l in i.get("labels", [])[:3]  # cap at 3 labels
        )
        comments_html = ""
        if i.get("comments", 0) > 0:
            comments_html = f'<span class="iss-comments">&#x1f4ac; {i["comments"]}</span>'
        labels_line = f"        {labels_html}\n" if labels_html else ""

        rows += f"""      <div class="iss-row">
        <a class="iss-num" href="{i['url']}" target="_blank" rel="noopener">#{i['number']}</a>
        <span class="iss-title">{esc(clip(i['title'], 85))}</span>
{labels_line}        <span class="iss-meta"><span class="iss-author">{esc(i['author'])}</span> <span class="iss-time">{i['ago']}</span>{comments_html}</span>
      </div>"""

    return f"""    <div class="dash-card full-width">
      <h3><i class="hgi hgi-stroke hgi-alert-02"></i> Issues <span class="card-count">{total_open:,} open &middot; {total_closed:,} closed</span></h3>
      <div class="iss-list">
{rows}
      </div>
    </div>"""


def prs_panel(state: dict) -> str:
    """Horizontal scroll strip of PR cards."""
    pr_data = state.get("pull_requests", {})
    items = pr_data.get("recent", [])
    total_open = pr_data.get("total_open", 0)
    total_closed = pr_data.get("total_closed", 0)

    if not items:
        return ""

    cards = ""
    for pr in items:
        status_badge = ""
        if pr.get("draft"):
            status_badge = '<span class="prs-status prs-draft">draft</span>'
        elif pr.get("review") == "APPROVED":
            status_badge = '<span class="prs-status prs-approved">approved</span>'
        elif pr.get("review") == "CHANGES_REQUESTED":
            status_badge = '<span class="prs-status prs-changes">changes req</span>'
        else:
            status_badge = '<span class="prs-status prs-open">open</span>'

        cards += f"""    <article class="prs-card">
      <div class="prs-header">
        <a class="prs-num" href="{pr['url']}" target="_blank" rel="noopener">#{pr['number']}</a>
        {status_badge}
        <span class="prs-time">{pr['ago']}</span>
      </div>
      <p class="prs-title">{esc(clip(pr['title'], 70))}</p>
      <div class="prs-footer">
        <span class="prs-author">by {esc(pr['author'])}</span>
        <span class="prs-diff"><span class="add">+{pr['additions']}</span> <span class="del">-{pr['deletions']}</span></span>
      </div>
    </article>"""

    return f"""    <div class="dash-card full-width">
      <h3><i class="hgi hgi-stroke hgi-git-pull-request"></i> Pull Requests <span class="card-count">{total_open:,} open &middot; {total_closed:,} closed</span></h3>
      <div class="prs-strip">
{cards}
      </div>
    </div>"""


def contributors_panel(state: dict) -> str:
    """Horizontal scroll strip of contributor avatar cards."""
    ct_data = state.get("contributors", {})
    contribs = ct_data.get("contributors", [])

    if not contribs:
        return ""

    cards = ""
    for c in contribs:
        cards += f"""      <a class="contrib-card" href="{c['html_url']}" target="_blank" rel="noopener">
        <img class="contrib-avatar" src="{esc(c['avatar_url'])}&s=64" alt="" loading="lazy" width="36" height="36">
        <span class="contrib-name">{esc(c['login'])}</span>
        <span class="contrib-count">{c['contributions']:,}</span>
      </a>"""

    return f"""    <div class="dash-card full-width">
      <h3><i class="hgi hgi-stroke hgi-user-group"></i> Top Contributors</h3>
      <div class="contrib-strip">
{cards}
      </div>
    </div>"""


def render_panels(state: dict) -> str:
    # Keep nested markers intact. Later passes fill each section.
    return f"""  <!-- ISSUES:START -->
  <!-- ISSUES:END -->
  <!-- PRS:START -->
  <!-- PRS:END -->
  <!-- CONTRIBUTORS:START -->
  <!-- CONTRIBUTORS:END -->
  <div class="dash-row">
{backlog_panel(state)}
{releases_panel(state)}
{merge_rate_panel(state)}
  </div>"""


# ── main ────────────────────────────────────────────────────────────────────

def main() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    page = INDEX.read_text(encoding="utf-8")

    # Remove stale section markers left after PANELS:END by older builds.
    # The live section markers must exist only inside the panels block.
    page = re.sub(
        re.escape(PANELS_END) + r".*?" + re.escape(NEWSLETTER_START),
        PANELS_END + "\n  " + NEWSLETTER_START,
        page,
        count=1,
        flags=re.S,
    )

    # Remove prior generated section bodies before rebuilding. This keeps
    # repeated refreshes idempotent, even after an interrupted build.
    for start, end in ((ISSUES_START, ISSUES_END),
                       (PRS_START, PRS_END),
                       (CONTRIBUTORS_START, CONTRIBUTORS_END)):
        page = re.sub(re.escape(start) + r".*?" + re.escape(end),
                      start + end, page, flags=re.S)

    for marker in (START, END, PANELS_START, PANELS_END, TICKER_START, TICKER_END, CSS_START, CSS_END, NEWSLETTER_START, NEWSLETTER_END, ISSUES_START, ISSUES_END, PRS_START, PRS_END, CONTRIBUTORS_START, CONTRIBUTORS_END):
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