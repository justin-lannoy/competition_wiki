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
- **Category** — one of `lto`, `bnpl`, `pos-financing`, `medical-financing`.
- **Search query** — optional. Overrides the news search for this competitor. Leave
  blank to auto-build from the name + parent. Use it to disambiguate short/generic
  names (e.g. `Zip`, `HFD`). Standard Google News query syntax (`"phrase" OR "phrase"`).

| Slug | Competitor | Parent (SEC issuer) | Ticker | Category | Search query | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| acima | Acima | Upbound Group | UPBD | lto | | Brand of Upbound Group (also Rent-A-Center) |
| affirm | Affirm Holdings | Affirm Holdings | AFRM | bnpl | | |
| koalafi | Koalafi | Koalafi (private) | private | pos-financing | | Privately held |
| healthcare-finance-direct | HFD (Healthcare Finance Direct) | Healthcare Finance Direct (private) | private | medical-financing | "Healthcare Finance Direct" | Patient / elective-medical financing |
| progressive-leasing | Progressive Leasing | PROG Holdings | PRG | lto | | |
| easypay-finance | EasyPay Finance | EasyPay Finance (private) | private | lto | "EasyPay Finance" OR "Duvera Billing" | Retail installment / lease-to-own |
| klarna | Klarna Group | Klarna Group | KLAR | bnpl | | Foreign filer (20-F / 6-K) |
| american-first-finance | American First Finance (AFF) | FirstCash Holdings | FCFS | lto | | Subsidiary of FirstCash Holdings |
| katapult | Katapult | Katapult Holdings | KPLT | lto | "Katapult" OR "Katapult Holdings" | E-commerce lease-to-own |
| kafene | Kafene | Kafene (private) | private | lto | | Privately held POS lease-to-own |
| zip | Zip | Zip Co Limited | ZIP.AX | bnpl | "Zip Co" OR "Zip Pay" OR Quadpay | ASX-listed; not a U.S. SEC filer (skipped in EDGAR) |
| sezzle | Sezzle | Sezzle Inc. | SEZL | bnpl | | |
| afterpay | Afterpay | Block, Inc. | XYZ | bnpl | "Afterpay" | Subsidiary of Block; filings are Block's consolidated reports |
| bread-financial | Bread Financial | Bread Financial Holdings | BFH | pos-financing | "Bread Financial" | |
| synchrony-financial | Synchrony Financial | Synchrony Financial | SYF | pos-financing | | |
