# competition_wiki Split — Migration Plan

> Companion to `2026-06-15-sec-filings-tracker.md`. Executes the 2026-06-15 pivot:
> break the competitor + SEC view into a standalone repo and keep partner-wiki light.

**Goal:** Stand up `/Users/jlannoy/Documents/GitHub/competition_wiki` as a full, standalone competitor-intelligence wiki (competitor pages + SEC filings tracker + a Competitor Watch landing tab), and leave `partner-wiki` as its original partner-focused self (native competitor tracking retained, SEC layer absent).

**Decisions (user, 2026-06-15):**
1. partner-wiki keeps native competitor tracking (pages/competitors + competitor moves); drops only the SEC layer. Since `main` never carried SEC code, partner-wiki's lighter version ≈ `main`.
2. competition_wiki = full standalone wiki (copy the SPA infra), seeded with competitor + SEC content, with the Competitor Watch tab built here.
3. Git: partner-wiki's lighter version is a fresh branch off `main`; the SEC feature branch (`feat/sec-filings-tracker`) is the source copied into competition_wiki and never merges to partner-wiki main.

## Source of truth
All SEC code/data lives on partner-wiki branch `feat/sec-filings-tracker`:
- `scripts/_lib.py` (with `parse_competitors`, `CompetitorFiler`, `parse_frontmatter`, `SEC_FILINGS_ROOT`), `scripts/sec_edgar.py`, `scripts/refresh_sec_filings.py`
- `tests/` (test_lib_competitors, test_sec_edgar, test_render_pages)
- `pages/sec-filings/` (index + 5 filer pages), `sec-filings/` (133 docs + 5 `_filings.json` + `company_tickers.json`, ~82 MB)
- `pages/competitors/` (6 pages) and the 37 event pages they reference

## Phase 1 — Scaffold competition_wiki (Task 7)
Into the existing `competition_wiki` repo (already `git init`'d, has README):
- Copy SPA infra from the feature branch working tree: `build_wiki.py`, `wiki_app.js`, `wiki_styles.css`, `wiki_enhance.js`, `index.html`, `manifest.json`, `requirements.txt`, `.gitignore`, `.env.example`.
- Copy `scripts/_lib.py`, `scripts/sec_edgar.py`, `scripts/refresh_sec_filings.py`.
- Copy `tests/` (all three test modules + `__init__.py`).
- Copy content: `pages/competitors/` (6), `pages/sec-filings/` (6), the 37 referenced `pages/events/*.md`, and `sec-filings/` (data).
- Edit `competition_wiki/build_wiki.py` `PAGE_DIRS` to add `("pages/sec-filings", "sec-filing")` (competitor + events dirs are already in the list; missing partner/sae/etc. dirs are skipped safely by `collect_pages`).

## Phase 2 — Competitor Watch as the landing tab (Task 8)
Adapt `competition_wiki/wiki_app.js` (this is the originally-planned Task 8, made the home view):
- Add `SEC_FILING_PAGES` / `SEC_FILING_MAP` (join competitor slug → tracker page via the tracker's `competitor: [[slug]]` frontmatter) and a `'sec-filing': 'SEC Filing'` `TYPE_LABELS` entry.
- Add `CompetitorView` (per competitor: header brand/parent/ticker, recent-move chips resolved from `[[event]]` links via `classifySignal`, and a "View N SEC filings →" deep-link to the tracker page).
- Add the `competitors` branch to the `App` content switch and a `competitors` command-palette action.
- Make Competitor Watch the **default** view (`useState('competitors')`) since there are no editions to land on.
- Trim the sidebar to competitor-relevant sections: Competitor Watch, the competitor list, and the SEC Filings index. Remove the SAE Books / Industries / Opportunities / Editions sections (those pages don't exist here).
- Build: `python3 build_wiki.py --no-embed-key`; confirm JSON round-trips and `sec-filing` pages are present.

## Phase 3 — Finalize competition_wiki (Task 9)
- Write `competition_wiki/README.md` (purpose, `refresh_sec_filings.py` usage, EDGAR etiquette, data layout).
- Add a `scripts/refresh_and_push.sh`-style weekly wrapper OR document the manual `python3 scripts/refresh_sec_filings.py --use-anthropic-api` cadence. (Keep minimal; no launchd plist unless requested.)
- Move the two SEC planning docs (`docs/superpowers/specs|plans/2026-06-15-sec-filings-tracker*.md`) into competition_wiki and this split plan alongside them.
- `git add` + commit the populated repo.

## Phase 4 — Lighten partner-wiki (Task 10)
- Create branch `chore/lighter-partner-wiki` off `main`.
- Remove the two SEC planning docs from partner-wiki (they now live in competition_wiki). No code changes — `main` has no SEC code; native competitor tracking stays.
- Leave `feat/sec-filings-tracker` intact as historical source; do NOT merge it to `main`.

## Verification
- `cd competition_wiki && python3 -m pytest tests/ -q` → unit tests pass (live EDGAR smoke skipped).
- `python3 build_wiki.py --no-embed-key` succeeds; `grep -c '"type": "sec-filing"' pages/wiki.html` ≥ 6.
- Open `competition_wiki/pages/wiki.html`: lands on Competitor Watch; all 6 competitors listed; public filers deep-link to tracker pages (table + summaries); Koalafi shows private.
- `competition_wiki/pages/sec-filings/` and `sec-filings/` present; `refresh_sec_filings.py --existing-only` re-renders offline.
- partner-wiki lighter branch: `pages/competitors/` intact, no `sec-filings/`, no SEC scripts.
