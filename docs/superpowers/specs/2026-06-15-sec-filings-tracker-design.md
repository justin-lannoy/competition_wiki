# SEC Filings Tracker for Public Competitors — Design

**Date:** 2026-06-15
**Status:** Approved (pending spec review)

## Problem

The wiki tracks competitor "moves" via web search, but has no primary-source
record of the competitors' SEC filings. We want to pull SEC filings for every
publicly traded competitor listed under `pages/competitors/`, store them in
their own directory, and track/manage them inside the wiki.

## Scope of competitors

Filer identity comes from each competitor page's frontmatter **`parent`** field
(the actual SEC issuer), not the brand name. `ticker: private` is skipped.

| Competitor page              | SEC filer (parent)  | Ticker | Notes                          |
| ---------------------------- | ------------------- | ------ | ------------------------------ |
| acima                        | Upbound Group       | UPBD   |                                |
| progressive-leasing          | PROG Holdings       | PRG    |                                |
| affirm                       | Affirm Holdings     | AFRM   |                                |
| american-first-finance       | FirstCash Holdings  | FCFS   | AFF reports as an FCFS segment |
| klarna                       | Klarna Group        | KLAR   | Foreign filer → 20-F / 6-K     |
| koalafi                      | *private*           | —      | Skipped                        |

The competitor universe is read at runtime from `pages/competitors/*.md`, so
adding/removing a competitor page automatically changes coverage on the next run.

## Data source: SEC EDGAR

EDGAR is the canonical free source — no API key required. Requirements:

- A descriptive `User-Agent` header carrying a contact email
  (`partner-wiki refresh_sec_filings.py jlannoy@snapfinance.com`).
- Rate limit ≤ 10 requests/sec — enforced with a small inter-request sleep.

Endpoints used:

- `https://www.sec.gov/files/company_tickers.json` — ticker → CIK map. Cached
  locally (refreshed when stale) to avoid re-downloading every run.
- `https://data.sec.gov/submissions/CIK{cik10}.json` — recent filings metadata
  per filer (`form`, `filingDate`, `reportDate`, `accessionNumber`,
  `primaryDocument`).
- Document URL:
  `https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodashes}/{primaryDocument}`

CIK is zero-padded to 10 digits for the submissions endpoint.

## Filing scope

- Form types: `10-K`, `10-Q`, `8-K`, plus `20-F` and `6-K` (Klarna, foreign
  private issuer).
- Rolling window: filings with `filingDate` within the last 730 days (24 months).

## Directory layout

```
sec-filings/                          # top-level; raw docs; COMMITTED to git
  upbound-group/
    _filings.json                     # metadata sidecar (enables offline rebuild)
    2026-02-15_10-K_0000933036-26-000012.htm
    2026-05-01_10-Q_0000933036-26-000045.htm
  affirm-holdings/
  prog-holdings/
  firstcash-holdings/
  klarna-group/

pages/sec-filings/                    # tracker pages; rendered in the wiki
  index.md                            # roll-up across all filers
  upbound-group.md                    # per-filer: filings table + AI summaries
  affirm-holdings.md
  prog-holdings.md
  firstcash-holdings.md
  klarna-group.md
```

- Filer slug: `_lib.slugify("Upbound Group") → "upbound-group"`.
- Downloaded filename pattern: `{filingDate}_{form}_{accession}.{ext}` — sorts
  chronologically and is unique per filing.
- Raw docs are committed to git (and pushed) per the approved git policy.

## Components & data flow

`scripts/refresh_sec_filings.py` (new), following the structure of
`scripts/refresh_industry_reports.py`:

1. **`parse_competitors()`** — new helper in `scripts/_lib.py`. Reads
   `pages/competitors/*.md`, parses frontmatter, and yields records of
   `(slug, title, parent, ticker)`, skipping `ticker: private`. Reuses the
   existing frontmatter conventions; the filer slug is derived from `parent`
   via `slugify`.
2. **CIK resolution** — load/cache `company_tickers.json`; map ticker → CIK.
   An unresolvable ticker logs a warning and skips that filer (non-fatal).
3. **Fetch + filter** — pull the submissions JSON per CIK; keep forms in
   `{10-K, 10-Q, 8-K, 20-F, 6-K}` filed within the last 730 days (24 months).
4. **Download docs + persist metadata** — fetch each in-scope primary document
   into `sec-filings/{filer}/`. Files already on disk are skipped (idempotent).
   Filing metadata (form, filingDate, reportDate, accession, primaryDocument,
   local filename, and any AI summary) is written to a per-filer sidecar
   `sec-filings/{filer}/_filings.json`. This sidecar is the source of truth for
   `--existing-only` rebuilds and for accession-keyed summary deduplication.
5. **AI summaries** — only under `--use-anthropic-api`. For each filing not yet
   summarized, strip the document to text, truncate to a token-safe budget, and
   ask Claude (`claude-sonnet-4-6`, matching the industry script) for a
   structured summary: key financials, segment notes, risk-factor changes,
   material events. Keyed by accession number so re-runs do not re-summarize;
   existing summaries are preserved across runs.
6. **Write tracker pages** — per-filer page with a filings table (form, date,
   period, EDGAR link, local doc link) plus the AI summaries; plus an
   `index.md` roll-up across all filers. Written via `_lib.write_page`.
7. **Rebuild wiki** — `python3 build_wiki.py --no-embed-key`.

### Flags

Mirroring `refresh_industry_reports.py`:

- `--use-anthropic-api` — download docs and generate/refresh AI summaries.
- `--existing-only` — rebuild tracker pages from local state only (downloaded
  docs + a persisted per-filer metadata sidecar; see below). Fully offline: no
  network, no Anthropic calls. Mirrors the industry script's offline refresh.
- `--dry-run` — list what would be downloaded/summarized without writing.

At least one of `--use-anthropic-api` / `--existing-only` is required (same
contract as the industry script).

## Competitor review tab (wiki UI)

A standalone **Competitor Watch** tab in the wiki gives a single place to review
the full situation for each public competitor — overview, recent moves,
read-through themes, *and* the SEC filings tracker side by side — rather than
scattering that across separate pages.

This follows the existing `IndustryView` precedent in `wiki_app.js`:

- **Routing** — `wiki_app.js` `App` component uses an `activeView` switch (the
  `ask` / `trends` / `industry` branches around lines 1388–1393). Add a
  `competitors` branch rendering a new `CompetitorView`.
- **`CompetitorView`** (new component, modeled on `IndustryView` at line 426) —
  a landing view that, for each entry in the existing `COMPETITOR_PAGES` array,
  shows: a header (brand, parent, ticker, category), classified recent-move
  chips (reusing the existing `classifySignal` / `SIGNALS` taxonomy), the
  read-through themes, and a **SEC filings panel** — the filer's recent filings
  table with form/date links and a click-through to the per-filer tracker page
  and AI summaries. Each competitor card deep-links to both the competitor page
  and its SEC tracker page via `navigateTo`.
- **Sidebar** — add a `Competitor Watch` section/entry in `Sidebar`
  (line 756), consistent with the `Industries` and `Opportunities` sections,
  with a count badge of competitors watched. Wire `setActiveView('competitors')`.
- **Command palette** — add a `competitors` action entry (the palette already
  supports view-switch actions, line 1286).
- **Linking SEC data into the view** — the tracker pages are type `sec-filing`
  with slug = filer slug; each competitor's `parent` slugifies to that filer
  slug, which is how `CompetitorView` joins a competitor to its filings. A
  lightweight `SEC_FILING_MAP` (filer-slug → tracker page), built alongside the
  existing `COMPETITOR_PAGES` map, performs the join.

Acceptance bar: the tab is reachable from the sidebar and command palette,
lists all watched competitors, and surfaces each one's SEC filings with
working deep-links.

## Wiki & automation integration

- **`build_wiki.py`** — add `("pages/sec-filings", "sec-filing")` to
  `PAGE_DIRS` so tracker pages are collected into `wiki.html` (this makes them
  available to `CompetitorView` and reachable as standalone pages).
- **`scripts/refresh_and_push.sh`**:
  - Step 8 `git add` allowlist gains `pages/sec-filings` and `sec-filings`.
  - A Monday hook runs `python3 scripts/refresh_sec_filings.py
    --use-anthropic-api`, **non-fatal** — non-zero exits are swallowed exactly
    like the existing industry-research hook, so an EDGAR or Anthropic hiccup
    never breaks the weekly commit/push. Off-Monday runs of the wrapper do not
    invoke the SEC script (the tracker tables are already on disk).
- **Optional** — a one-line backlink from each competitor page to its tracker
  page (and the tracker page links back to the competitor). Nice-to-have, not
  required for acceptance.

## Error handling

- Network / rate-limit errors: retry with backoff; on persistent failure, skip
  the affected filer and continue. The script never aborts the weekly push.
- EDGAR etiquette: descriptive `User-Agent` + inter-request sleep on every call.
- Foreign or missing CIK: warn and skip.
- Document download failure for one filing does not abort the filer; the filing
  is recorded in the table without a local-doc link and retried next run.

## Testing

- **Dry-run** lists the filers resolved, CIKs found, and filings that would be
  downloaded/summarized — no writes.
- **Idempotency**: a second consecutive run downloads no new files and
  generates no new summaries.
- **Build**: `build_wiki.py --no-embed-key` succeeds and the embedded JSON
  round-trips (the script's existing sanity check).
- **Reachability**: tracker pages appear in the built wiki and render their
  filings table.
- **Competitor tab**: the Competitor Watch tab opens from the sidebar and
  command palette, lists every watched competitor, and each card's deep-links
  (to the competitor page and the SEC tracker page) resolve.

## Out of scope

- Full-text search / financial-statement XBRL parsing (only primary-document
  text is summarized).
- Historical backfill beyond the rolling 24-month window.
- Diffing risk-factor sections across filings (the summary may note changes,
  but no structured diff engine).
