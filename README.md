# competition_wiki

A standalone competitor-intelligence wiki for Snap Finance: it tracks lease-to-own /
POS-financing competitors and their **SEC filings**, and renders a self-contained
`pages/wiki.html` single-page app whose home view is a **Competitor Watch** dashboard.

Split out of `partner-wiki` on 2026-06-15 to hold the full competitor + SEC view, while
`partner-wiki` stays partner/SAE/industry focused.

## Quick start

```bash
cp .env.example .env                 # add ANTHROPIC_API_KEY for filing summaries
python3 scripts/refresh_sec_filings.py --use-anthropic-api   # pull + summarize
python3 build_wiki.py --no-embed-key                          # build pages/wiki.html
open pages/wiki.html                                          # view the wiki
```

- `--existing-only` re-renders the wiki from local data with no network/API calls.
- `--dry-run` reports what would be pulled without writing.
- Tests: `python3 -m pytest tests/ -q` (add `EDGAR_LIVE=1` for the live EDGAR smoke test).

## What's tracked

Public filers (10-K/10-Q/8-K, +20-F/6-K for foreign filers), last 24 months:
Upbound Group (UPBD), Affirm Holdings (AFRM), PROG Holdings (PRG),
FirstCash Holdings (FCFS), Klarna Group (KLAR). Koalafi is private (no filings).

## More

See **CLAUDE.md** for architecture, conventions, and how the pipeline works, and
`docs/superpowers/` for the design spec and migration/implementation plans.

Data source: U.S. SEC EDGAR (no API key required; uses a contact `User-Agent` and a
≤10 req/s rate limit). Raw filing documents are committed under `sec-filings/`.
