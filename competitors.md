# Competitor Registry

**Single source of truth for the competitors this wiki tracks.** The SEC filings
pipeline (`scripts/refresh_sec_filings.py`) and the wiki's Competitor Watch view
(`build_wiki.py`) both read the table below.

## How to edit

- **Add a competitor:** add a row. The next `build_wiki.py` / refresh picks it up.
- **Remove one:** delete its row.
- **Slug** — kebab-case id. If a matching `pages/competitors/<slug>.md` exists, its
  body is used as the competitor's editorial content; otherwise a stub is generated.
- **Parent (SEC issuer)** — the entity that files with the U.S. SEC (often differs
  from the brand). Used to resolve the SEC tracker.
- **Ticker** — U.S. exchange symbol for SEC tracking, or `private` to list the
  competitor without pulling SEC filings. A non-U.S. symbol (e.g. `ZIP.AX`) is kept
  for reference but will not resolve in EDGAR (the filer is skipped cleanly).
- **Category** — one of `lto`, `bnpl`, `pos-financing`, `medical-financing` (validated).
- **Tier** — competitive proximity to Snap: `direct-lto` (head-to-head for the same
  non-prime customer), `adjacent-bnpl` (prime/near-prime, competes upstream in the
  waterfall), `prime-card` (prime card issuers), `medical` (patient financing). The
  Competitor Watch view groups by this.
- **Product** — credit structure: `lease`, `RIC` (retail installment), `loan`,
  `card`, or `hybrid`. Drives regulatory exposure and the Snap-vs-competitor pitch.
- **Search query** — optional. Overrides the news search for this competitor. Leave
  blank to auto-build from the name + parent. Use it to disambiguate short/generic
  names (e.g. `Zip`, `HFD`). Standard Google News query syntax (`"phrase" OR "phrase"`).
- **PR feed** — optional RSS/Atom URL for the company's official newsroom or blog,
  pulled alongside Google News. The right channel for low-press private firms whose
  name has little/no news-outlet coverage (e.g. HFD → `https://gohfd.com/feed/`).

| Slug | Competitor | Parent (SEC issuer) | Ticker | Category | Tier | Product | Search query | PR feed | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| acima | Acima | Upbound Group | UPBD | lto | direct-lto | lease | | | Brand of Upbound Group (also Rent-A-Center) |
| progressive-leasing | Progressive Leasing | PROG Holdings | PRG | lto | direct-lto | lease | | | |
| american-first-finance | American First Finance (AFF) | FirstCash Holdings | FCFS | lto | direct-lto | hybrid | | | Subsidiary of FirstCash Holdings |
| katapult | Katapult | Katapult Holdings | KPLT | lto | direct-lto | lease | "Katapult" OR "Katapult Holdings" | | E-commerce lease-to-own; merging into Aaron's/CCFI |
| koalafi | Koalafi | Koalafi (private) | private | pos-financing | direct-lto | hybrid | | | Privately held; prime waterfall + LTO backstop |
| easypay-finance | EasyPay Finance | EasyPay Finance (private) | private | lto | direct-lto | RIC | "EasyPay Finance" OR "Duvera Billing" | | Retail installment / lease-to-own |
| kafene | Kafene | Kafene (private) | private | lto | direct-lto | lease | | | Privately held POS lease-to-own |
| uown | Uown Leasing | Uown (private) | private | lto | direct-lto | lease | "Uown Leasing" | | Privately held POS lease-to-own |
| sunbit | Sunbit | Sunbit (private) | private | pos-financing | direct-lto | loan | "Sunbit" | | Near/non-prime POS lending: auto-repair, dental, optical |
| genesis-credit | Genesis Credit | Genesis Financial Solutions (private) | private | pos-financing | direct-lto | card | "Genesis Credit" OR "Genesis Financial Solutions" OR "Concora Credit" | | Second-look / non-prime private-label card |
| affirm | Affirm Holdings | Affirm Holdings | AFRM | bnpl | adjacent-bnpl | loan | | | |
| klarna | Klarna Group | Klarna Group | KLAR | bnpl | adjacent-bnpl | loan | | | Foreign filer (20-F / 6-K) |
| sezzle | Sezzle | Sezzle Inc. | SEZL | bnpl | adjacent-bnpl | loan | | | |
| afterpay | Afterpay | Block, Inc. | XYZ | bnpl | adjacent-bnpl | loan | "Afterpay" | | Subsidiary of Block; filings are Block's consolidated reports |
| zip | Zip | Zip Co Limited | ZIP.AX | bnpl | adjacent-bnpl | loan | "Zip Co" OR "Zip Pay" OR Quadpay | | ASX-listed; not a U.S. SEC filer (skipped in EDGAR) |
| bread-financial | Bread Financial | Bread Financial Holdings | BFH | pos-financing | prime-card | card | "Bread Financial" | | |
| synchrony-financial | Synchrony Financial | Synchrony Financial | SYF | pos-financing | prime-card | card | | | |
| healthcare-finance-direct | HFD (Healthcare Finance Direct) | Healthcare Finance Direct (private) | private | medical-financing | medical | loan | "Healthcare Finance Direct" | https://gohfd.com/feed/ | Rebranded to HFD; coverage from official PR feed |
| scratchpay | Scratchpay | Scratchpay (private) | private | medical-financing | medical | loan | "Scratchpay" | | Veterinary / pet patient financing |
