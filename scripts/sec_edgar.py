#!/usr/bin/env python3
"""SEC EDGAR client and pure helpers for the filings tracker (stdlib only).

EDGAR requires a descriptive User-Agent with a contact email and limits
callers to <=10 requests/sec. This module keeps the network surface tiny
(`EdgarClient`) and the data-shaping logic pure and unit-testable.
"""
from __future__ import annotations

import datetime as dt
import html as _html
import json
import re
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

EDGAR_UA = "Snap Finance partner-wiki refresh_sec_filings.py jlannoy@snapfinance.com"
TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"
ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"
DEFAULT_FORMS = ("10-K", "10-Q", "8-K", "20-F", "6-K")
MIN_INTERVAL = 0.15  # seconds between requests — comfortably under 10/sec

COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json"
# Revenue is tagged differently across filers; try TOTAL-revenue tags first.
# "Revenues" is the consolidated top line; the contract-revenue tags are often
# a partial line; banks (Synchrony/Bread) report interest & fee income instead.
REVENUE_CONCEPTS = (
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "InterestAndFeeIncomeLoansAndLeases",
)
NETINCOME_CONCEPTS = ("NetIncomeLoss",)
OPERATING_INCOME_CONCEPTS = ("OperatingIncomeLoss",)
GROSS_PROFIT_CONCEPTS = ("GrossProfit",)
EPS_CONCEPTS = ("EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted")

# Metric -> (concept candidates, XBRL unit). Drives the financials extraction.
FINANCIAL_METRICS = {
    "revenue": (REVENUE_CONCEPTS, "USD"),
    "net_income": (NETINCOME_CONCEPTS, "USD"),
    "operating_income": (OPERATING_INCOME_CONCEPTS, "USD"),
    "gross_profit": (GROSS_PROFIT_CONCEPTS, "USD"),
    "eps_diluted": (EPS_CONCEPTS, "USD/shares"),
}


def ratio_series(numer: list[dict], denom: list[dict], *, pct: bool = True) -> list[dict]:
    """Per-period ratio of two series aligned by `end` date (e.g. net margin =
    net income / revenue). Returns [{end, val, label}] for shared periods."""
    by_end = {d["end"]: d for d in denom}
    out = []
    for n in numer:
        d = by_end.get(n["end"])
        if d and d["val"]:
            v = n["val"] / d["val"] * (100 if pct else 1)
            out.append({"end": n["end"], "val": v, "label": n["label"]})
    return out


def extract_quarterly_series(facts: dict, concepts: tuple[str, ...], *,
                             unit: str = "USD",
                             max_points: int = 8, recent_years: int = 4,
                             today: "dt.date | None" = None) -> list[dict]:
    """Pull up to `max_points` recent ~quarterly data points for the first
    matching us-gaap concept from an XBRL companyfacts payload.

    Returns [{end, val, label}] sorted oldest→newest. Filters to ~quarterly
    durations (80–100 days) from 10-Q/10-K (so annual and quarterly aren't
    mixed) AND to the last `recent_years` (so a concept a filer abandoned years
    ago isn't charted as if current). Returns [] if no concept yields ≥2 points.
    """
    today = today or dt.date.today()
    cutoff = (today - dt.timedelta(days=int(365.25 * recent_years))).isoformat()
    usgaap = (facts or {}).get("facts", {}).get("us-gaap", {})
    for concept in concepts:
        vals = (usgaap.get(concept) or {}).get("units", {}).get(unit)
        if not vals:
            continue
        by_end: dict[str, dict] = {}
        for it in vals:
            start, end, val = it.get("start"), it.get("end"), it.get("val")
            if (not (start and end and val is not None)
                    or it.get("form") not in ("10-Q", "10-K") or end < cutoff):
                continue
            try:
                days = (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days
            except (ValueError, TypeError):
                continue
            if not (80 <= days <= 100):   # quarterly only
                continue
            by_end[end] = {
                "end": end, "val": float(val),
                "label": f"{it.get('fp') or ''} {it.get('fy') or ''}".strip() or end,
            }
        series = [by_end[k] for k in sorted(by_end)][-max_points:]
        if len(series) >= 2:
            return series
    return []


@dataclass(frozen=True)
class Filing:
    form: str
    filing_date: str    # ISO "YYYY-MM-DD"
    report_date: str
    accession: str      # "0000933036-26-000012"
    primary_doc: str    # "upbd-20251231.htm"
    description: str


def cik_from_ticker(ticker_map: dict, ticker: str) -> str | None:
    """Resolve a ticker to a 10-digit zero-padded CIK using company_tickers.json."""
    want = ticker.strip().upper()
    for row in ticker_map.values():
        if str(row.get("ticker", "")).upper() == want:
            return str(row["cik_str"]).zfill(10)
    return None


def filing_filename(f: Filing) -> str:
    """Stable, sortable, unique on-disk name: {date}_{form}_{accession}.{ext}."""
    ext = f.primary_doc.rsplit(".", 1)[-1] if "." in f.primary_doc else "htm"
    safe_form = f.form.replace("/", "-")
    return f"{f.filing_date}_{safe_form}_{f.accession}.{ext}"


def filter_filings(recent: dict, today: dt.date, *,
                   forms: tuple[str, ...] = DEFAULT_FORMS,
                   days: int = 730) -> list[Filing]:
    """Select in-scope filings from a submissions `filings.recent` block.

    Keeps forms in `forms` filed within the last `days` days. The `recent`
    arrays are parallel (EDGAR's columnar layout)."""
    cutoff = today - dt.timedelta(days=days)
    forms_set = set(forms)
    accs = recent.get("accessionNumber", [])
    n = len(accs)
    forms_col = recent.get("form", [])
    fdates = recent.get("filingDate", [])
    rdates = recent.get("reportDate", [])
    docs = recent.get("primaryDocument", [])
    descs = recent.get("primaryDocDescription", [])
    out: list[Filing] = []
    for i in range(n):
        # `form` and `filingDate` are the two required columns; if EDGAR ever
        # returns a block missing them (partial/changed schema) we skip the row
        # rather than raise, mirroring the defensive .get on the other columns.
        if i >= len(forms_col) or i >= len(fdates):
            continue
        form = forms_col[i]
        if form not in forms_set:
            continue
        fdate = fdates[i]
        try:
            d = dt.date.fromisoformat(fdate)
        except (ValueError, TypeError):
            continue
        if d < cutoff:
            continue
        out.append(Filing(
            form=form,
            filing_date=fdate,
            report_date=(rdates[i] if i < len(rdates) else "") or "",
            accession=accs[i],
            primary_doc=(docs[i] if i < len(docs) else "") or "",
            description=(descs[i] if i < len(descs) else "") or "",
        ))
    return out


def edgar_doc_url(cik10: str, accession: str, primary_doc: str) -> str:
    """Build the public document URL (Archives path uses unpadded CIK)."""
    return ARCHIVES_URL.format(
        cik=str(int(cik10)),
        acc=accession.replace("-", ""),
        doc=primary_doc,
    )


def html_to_text(raw: "bytes | str") -> str:
    """Crude HTML/XBRL -> plain text for summarization input.

    Note: does not handle `>` inside attribute values, so stray attribute text
    may leak into the output. Adequate for LLM summarization; do not use for
    display.
    """
    text = raw.decode("utf-8", "ignore") if isinstance(raw, bytes) else raw
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = _html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def truncate_for_model(text: str, max_chars: int = 120_000) -> str:
    """Clip text to fit a model context window (~120k chars ≈ 30k tokens for Sonnet)."""
    return text[:max_chars]


def load_sidecar(path: Path) -> dict:
    """Read a per-filer _filings.json sidecar; {} if missing or corrupt."""
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def merge_sidecar(existing: dict, cik10: str, filings: list[Filing],
                  local_names: dict[str, str]) -> dict:
    """Merge freshly fetched filings into a sidecar, keyed by accession.

    Preserves any prior `summary` and falls back to the prior `local_file`
    when this run didn't (re)download the doc. Returns a new dict; does not
    mutate `existing`."""
    prev = existing.get("filings", {})
    if not isinstance(prev, dict):
        prev = {}
    by_acc: dict[str, dict] = dict(prev)
    for f in filings:
        old = by_acc.get(f.accession, {})
        by_acc[f.accession] = {
            "form": f.form,
            "filing_date": f.filing_date,
            "report_date": f.report_date,
            "accession": f.accession,
            "primary_doc": f.primary_doc,
            "description": f.description,
            "local_file": local_names.get(f.accession) or old.get("local_file", ""),
            "summary": old.get("summary", ""),
        }
    return {"cik": cik10, "filings": by_acc}


class EdgarClient:
    """Rate-limited EDGAR fetcher. One instance per refresh run."""

    def __init__(self, cache_dir: Path, ua: str = EDGAR_UA):
        self.cache_dir = cache_dir
        self.ua = ua
        self._last = 0.0
        self._ticker_map: dict | None = None

    def _get(self, url: str) -> bytes:
        wait = MIN_INTERVAL - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(url, headers={
            "User-Agent": self.ua,
            "Accept-Encoding": "identity",   # avoid gzip; keep parsing trivial
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()
        finally:
            self._last = time.monotonic()

    def ticker_map(self, max_age_days: int = 7) -> dict:
        """company_tickers.json, cached on disk and refreshed weekly."""
        if self._ticker_map is not None:
            return self._ticker_map
        cache = self.cache_dir / "company_tickers.json"
        if cache.exists():
            age = dt.date.today() - dt.date.fromtimestamp(cache.stat().st_mtime)
            if age.days <= max_age_days:
                try:
                    self._ticker_map = json.loads(cache.read_text(encoding="utf-8"))
                    return self._ticker_map
                except (json.JSONDecodeError, OSError):
                    pass  # corrupt/partial cache — fall through and re-fetch
        data = self._get(TICKER_MAP_URL)
        cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache.with_suffix(".tmp")  # atomic write so a killed run can't leave a corrupt cache
        tmp.write_bytes(data)
        tmp.replace(cache)
        self._ticker_map = json.loads(data)
        return self._ticker_map

    def submissions(self, cik10: str) -> dict:
        return json.loads(self._get(SUBMISSIONS_URL.format(cik10=cik10)))

    def companyfacts(self, cik10: str) -> dict:
        """XBRL company facts (structured financial time-series). {} on 404."""
        try:
            return json.loads(self._get(COMPANYFACTS_URL.format(cik10=cik10)))
        except Exception:
            return {}

    def download(self, cik10: str, f: Filing, dest: Path) -> bool:
        """Download a filing's primary document to `dest`. Returns False if it
        already exists (idempotent). Writes atomically via a .tmp rename."""
        if dest.exists():
            return False
        data = self._get(edgar_doc_url(cik10, f.accession, f.primary_doc))
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(dest)
        return True
