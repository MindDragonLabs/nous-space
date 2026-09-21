# Mission Ledger lower-page redesign

## Design source

- Visual research lane: mempool.space operational density and ruled data surfaces.
- Art direction: **Mission Ledger** — flat lower-page records, small stage labels, restrained color, no generic card gallery.
- UX audit: Chromium measurements of the pre-change page at 390, 768, 1280, and 1440 widths.

## Changed

- Replaced oversized lower newsletter cards with a compact linked **Now / Wire** rail.
- Replaced PR card carousel with full-width linked PR ledger rows.
- Reworked issue rows as full-row links with readable metadata and comment text.
- Reworked contributor avatar tiles as a ranked contributor ledger.
- Added semantic lower section IDs: `#now`, `#issues`, `#prs`, `#contributors`.
- Added Mission Ledger visual tokens, ruled surfaces, compact rows, focus rings, responsive breakpoints, and reduced-motion handling.
- Removed the dead lower-page `.search-bar` geometry that expanded the nav beyond mobile viewport width.
- Kept the top navigation, isometric strip, and three summary cards unchanged in content and structure.

## Verification

Commands run:

```text
python3 -m py_compile build.py fetch_state.py refresh_data.py
python3 build.py
python3 build.py
git diff --check
```

Observed:

```text
index.html rendered — green: #115502, #115506, #115515, #115645, #115682 | blue: #118082, #118097, #118021, #118006, #118027
index.html unchanged
```

HTTP checks:

```text
local:200
public:200
```

Chrome DevTools Protocol checks against `file:///Users/jefferson/nous-space/index.html`:

- **1440 viewport:** document scroll width 1425 and client width 1425; lower deck 1160px wide; lower sections 1120px wide; representative issue row 46px high; `#now`, `#issues`, `#prs`, and `#contributors` all present; ticker animation `none`.
- **390 viewport:** document scroll width 375 and client width 375; lower deck 347px wide; lower sections 327px wide; representative issue row 156px high because title and metadata wrap cleanly; all four sections present; ticker animation `none`.

The 390px page-wide overflow measured before this change was +269px (659 vs 390). It is now zero.
