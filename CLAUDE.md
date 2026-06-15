# CLAUDE.md — competition_wiki

Guidance for AI agents (and humans) working in this repo. Read this first.

## What this repo is

**competition_wiki** is a standalone competitor-intelligence wiki for Snap Finance.
It tracks Snap's lease-to-own / POS-financing competitors and their **SEC filings**,
and renders everything as a single self-contained `pages/wiki.html` SPA whose home
view is a **Competitor Watch** dashboard.

It was split out of `partner-wiki` on 2026-06-15. The competitor + SEC-filings
"robust view" lives here; `partner-wiki` kept its partner/SAE/industry focus and a
lighter native competitor reference. The two repos share the same wiki SPA
machinery (`build_wiki.py`, `wiki_app.js`, `wiki_styles.css`) but are independent.

## Layout

```
build_wiki.py            Compiles every pages/**/*.md into pages/wiki.html (one SPA).
wiki_app.js              The React app (Babel-in-browser). Home view = Competitor Watch.
wiki_styles.css          Styles. wiki_enhance.js = progressive enhancement.
scripts/
  _lib.py                Shared helpers: slugify, write_page, parse_frontmatter,
                         parse_competitors() + CompetitorFiler, SEC_FILINGS_ROOT.
  sec_edgar.py           Stdlib-only SEC EDGAR client + pure helpers (CIK lookup,
                         filing filter (24-month window), sidecar load/merge, EdgarClient).
  refresh_sec_filings.py Orchestrator: pull filings → download docs → AI summaries →
                         render tracker pages → rebuild wiki.
tests/                   pytest unit tests for the pure logic (no network).
competitors.md           Single source of truth: the competitor roster (markdown
                         table). Add/remove a row to track/untrack a competitor.
pages/
  competitors/           OPTIONAL editorial page per competitor (body only; roster
                         fields come from competitors.md). New competitors render
                         from the registry with a generated stub if no page exists.
  events/                Competitor "moves" the competitor pages link to.
  sec-filings/           index.md + one tracker page per public filer (generated).
sec-filings/             Raw downloaded filing docs + per-filer _filings.json sidecars
                         + company_tickers.json cache. ~82 MB, committed on purpose.
docs/superpowers/        Design spec + implementation/migration plans (history).
```

## How the SEC pipeline works

1. `parse_competitors()` reads the `competitors.md` registry table; the SEC filer
   is the row's `Parent` (e.g. Acima → Upbound Group / UPBD). `ticker: private`
   (Koalafi) is skipped; a non-US symbol like `ZIP.AX` is kept but won't resolve in
   EDGAR (filer skipped cleanly). `build_wiki.py` reads the same registry to render
   the Competitor Watch roster, merging editorial bodies from `pages/competitors/`.
2. `EdgarClient` resolves ticker→CIK via `company_tickers.json`, pulls each filer's
   submissions JSON, and `filter_filings` keeps 10-K/10-Q/8-K (+20-F/6-K for foreign
   filers like Klarna) from the **last 730 days (24 months)**.
3. Primary documents download to `sec-filings/<filer-slug>/`; metadata + AI summaries
   persist to that filer's `_filings.json` sidecar (keyed by accession → idempotent).
4. `summarize_filing` asks Claude (`claude-sonnet-4-6`) for a structured summary.
5. `render_filer_page`/`render_index` write `pages/sec-filings/`; the wiki rebuilds.

## Running it

```bash
# one-time: provide the Anthropic key for summaries
cp .env.example .env && echo 'ANTHROPIC_API_KEY=sk-ant-...' >> .env

python3 scripts/refresh_sec_filings.py --use-anthropic-api   # pull + download + summarize
python3 scripts/refresh_sec_filings.py --existing-only        # re-render offline (no network/API)
python3 scripts/refresh_sec_filings.py --use-anthropic-api --dry-run
python3 build_wiki.py --no-embed-key                          # rebuild pages/wiki.html

python3 -m pytest tests/ -q                                   # unit tests
EDGAR_LIVE=1 python3 -m pytest tests/ -q                      # incl. live EDGAR smoke test
```

EDGAR needs **no API key** — just the descriptive `User-Agent` already set in
`sec_edgar.EDGAR_UA` (contact: jlannoy@snapfinance.com) and ≤10 req/s (enforced by
`MIN_INTERVAL`). Be a good citizen; don't remove the rate limit.

## Conventions / gotchas

- **Stdlib-only** Python pipeline (plus `anthropic`, `openpyxl`). Do NOT add
  `requests` or other deps — `sec_edgar.py` uses `urllib` deliberately.
- `build_wiki.py` embeds `wiki_app.js` as **text** — it does NOT validate JS/JSX.
  After editing `wiki_app.js`, open `pages/wiki.html` in a browser to confirm it
  renders (a JSX typo won't fail the build).
- Always rebuild with `--no-embed-key` so no live API key lands in the committed HTML.
- The competitor↔SEC join is data-driven: a tracker page carries
  `competitor: [[slug]]` frontmatter; `wiki_app.js` builds `SEC_FILING_MAP` from it
  (no slug recomputation in JS).
- Raw filing docs ARE committed (full archive, per project decision). Expect the repo
  to grow; weekly pushes get heavier.
- Adding/removing a competitor = add/remove a row in `competitors.md` (Slug, Parent,
  Ticker, Category); the next refresh + `build_wiki.py` pick it up automatically. An
  optional `pages/competitors/<slug>.md` supplies editorial body content.

## Status / where to resume

See `docs/superpowers/plans/2026-06-15-competition-wiki-split.md` (migration plan) and
`2026-06-15-sec-filings-tracker.md` (original feature plan + task-by-task history).
The SEC pipeline (Tasks 1–6) is built and verified; this repo was scaffolded and the
Competitor Watch tab made the landing view. Not yet wired: a scheduled/automated
weekly refresh (currently run manually — see commands above).
