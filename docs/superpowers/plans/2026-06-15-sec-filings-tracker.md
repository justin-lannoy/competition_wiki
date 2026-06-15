# SEC Filings Tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pull SEC filings for every publicly traded competitor under `pages/competitors/`, store the docs in a dedicated `sec-filings/` directory, render per-filer tracker pages with AI summaries, and add a standalone Competitor Watch tab to the wiki.

**Architecture:** A new stdlib-only EDGAR client (`scripts/sec_edgar.py`) fetches filing metadata and documents; a `_lib.py` helper enumerates public competitors from page frontmatter; an orchestrator (`scripts/refresh_sec_filings.py`) downloads docs, persists a per-filer `_filings.json` sidecar, generates Claude summaries, writes tracker pages under `pages/sec-filings/`, and rebuilds the wiki. The front-end gains a `CompetitorView` that joins each competitor to its filings tracker. Weekly automation hooks into `refresh_and_push.sh` non-fatally.

**Tech Stack:** Python 3 (stdlib `urllib`, `json`, `datetime`; `anthropic` for summaries), pytest, React (via `wiki_app.js` Babel-in-browser), bash.

**Spec:** `docs/superpowers/specs/2026-06-15-sec-filings-tracker-design.md`

---

## ⚠️ STATUS / HANDOFF — 2026-06-15

**Branch:** `feat/sec-filings-tracker` (off `main`). All work below is committed there.

**Done (Tasks 1–6), each via TDD + two-stage review (spec ✓ then code-quality ✓):**
- **Task 1** `parse_competitors()` + `CompetitorFiler` + `parse_frontmatter` + `SEC_FILINGS_ROOT` in `scripts/_lib.py` (commits `af621da`, `2c783ff`).
- **Task 2** pure EDGAR helpers in `scripts/sec_edgar.py` — `Filing`, `cik_from_ticker`, `filter_filings` (**24-month/730-day** window), `filing_filename`, `edgar_doc_url`, `html_to_text`, `truncate_for_model`, `load_sidecar`, `merge_sidecar` (`3f92565`, `5b12a9a`).
- **Task 3** `EdgarClient` (rate-limited, cached ticker map, atomic download) in `scripts/sec_edgar.py` (`f30d73a`, `549f9a7`).
- **Task 4** `render_filer_page` + `render_index` (+ `_cell` pipe-escape) in `scripts/refresh_sec_filings.py` (`a0196b9`, `eb2f076`).
- **Task 5** `summarize_filing` + `SUMMARY_SYSTEM` (`19d1b32`, `aff8a20`).
- **Task 6** orchestrator `main`/`_process_filer`/`_load_env` (`0db8c69`). **Real run pulled 133 filings across 5 filers, all summarized; idempotent; `--existing-only` offline render works.** Outputs: `sec-filings/<filer>/` (133 docs + `_filings.json` + `company_tickers.json`) and `pages/sec-filings/` (index + 5 filer pages).
- Test suite: **15 passed, 1 skipped** (live EDGAR smoke test, gated by `EDGAR_LIVE=1`).

**Tasks 7–10 (build_wiki PAGE_DIRS, Competitor Watch tab in wiki_app.js, weekly Monday hook, docs): NOT STARTED — and now SUPERSEDED.**

**PIVOT (user instruction 2026-06-15):** Break the competitor function out into a NEW repo `/Users/jlannoy/Documents/GitHub/competition_wiki` (the fully robust competitor + SEC view) and reduce partner-wiki back to a lighter, partner-focused version. The original Tasks 7–8 (which integrated the competitor/SEC view INTO partner-wiki's SPA) move to the new repo instead. A separate migration plan governs the split — see `docs/superpowers/plans/2026-06-15-competition-wiki-split.md` (to be written). Resume there.

---

## File Structure

**Create:**
- `scripts/sec_edgar.py` — EDGAR client + pure helpers (CIK lookup, filing filter, filename, HTML→text, sidecar merge).
- `scripts/refresh_sec_filings.py` — orchestrator: flags, download loop, summaries, page rendering, wiki rebuild.
- `tests/__init__.py` — empty (marks package).
- `tests/test_lib_competitors.py` — unit tests for `parse_competitors`.
- `tests/test_sec_edgar.py` — unit tests for the pure EDGAR helpers.
- `tests/test_render_pages.py` — unit tests for tracker-page rendering.

**Modify:**
- `scripts/_lib.py` — add `SEC_FILINGS_ROOT`, `parse_frontmatter`, `CompetitorFiler`, `parse_competitors`.
- `build_wiki.py:54-63` — add `("pages/sec-filings", "sec-filing")` to `PAGE_DIRS`.
- `wiki_app.js` — `SEC_FILING_PAGES`/`SEC_FILING_MAP` maps, `TYPE_LABELS` entry, `CompetitorView` component, `App` routing branch, `Sidebar` entry, command-palette action.
- `scripts/refresh_and_push.sh:139-142` (git-add allowlist) and after `:125` (Monday hook).

**Conventions to follow:** all Python writes go through `_lib.write_page`; scripts resolve paths from `WIKI_ROOT`/`PAGES`; wiki rebuild is always `python3 build_wiki.py --no-embed-key`; `.env` is loaded line-by-line (see `refresh_industry_reports.py:287-293`).

---

## Task 1: `parse_competitors` helper in `_lib.py`

Enumerate publicly traded competitors from `pages/competitors/*.md` frontmatter, deriving the SEC filer slug from the `parent` field.

**Files:**
- Modify: `scripts/_lib.py`
- Test: `tests/test_lib_competitors.py`, `tests/__init__.py`

- [ ] **Step 1: Write the failing test**

Create `tests/__init__.py` (empty file).

Create `tests/test_lib_competitors.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from _lib import parse_competitors, CompetitorFiler  # noqa: E402


def _write(dir_: Path, name: str, fm: str) -> None:
    (dir_ / name).write_text(fm, encoding="utf-8")


def test_parse_competitors_extracts_public_filers(tmp_path):
    _write(tmp_path, "acima.md",
           "---\ntitle: Acima\ntype: competitor\nparent: Upbound Group\n"
           "ticker: UPBD\ncategory: lto\n---\n\n# Acima\n")
    _write(tmp_path, "koalafi.md",
           "---\ntitle: Koalafi\ntype: competitor\nparent: Koalafi (private)\n"
           "ticker: private\ncategory: pos-financing\n---\n\n# Koalafi\n")
    _write(tmp_path, "klarna.md",
           "---\ntitle: Klarna Group\ntype: competitor\nparent: Klarna Group\n"
           "ticker: KLAR\ncategory: bnpl\n---\n\n# Klarna\n")

    filers = parse_competitors(tmp_path)

    assert all(isinstance(f, CompetitorFiler) for f in filers)
    slugs = {f.slug for f in filers}
    assert slugs == {"acima", "klarna"}            # private skipped
    acima = next(f for f in filers if f.slug == "acima")
    assert acima.parent == "Upbound Group"
    assert acima.ticker == "UPBD"
    assert acima.filer_slug == "upbound-group"      # slugify(parent)


def test_parse_competitors_skips_missing_parent(tmp_path):
    _write(tmp_path, "x.md",
           "---\ntitle: X\ntype: competitor\nticker: XYZ\n---\n\n# X\n")
    assert parse_competitors(tmp_path) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/jlannoy/Documents/GitHub/partner-wiki && python3 -m pytest tests/test_lib_competitors.py -v`
Expected: FAIL with `ImportError: cannot import name 'parse_competitors'`.

- [ ] **Step 3: Add the implementation to `scripts/_lib.py`**

Add near the top, after the `PAGES = WIKI_ROOT / "pages"` line (around line 18):

```python
SEC_FILINGS_ROOT = WIKI_ROOT / "sec-filings"
```

Add this frontmatter parser in the "Slugging" region (after `slugify`, around line 86) — a local copy so `_lib` has no import side effects (importing `build_wiki` would run its module-level `os.chdir`):

```python
def parse_frontmatter(text: str) -> dict:
    """Minimal YAML frontmatter parser (same dialect as build_wiki.py)."""
    fm: dict = {}
    if not text.startswith("---"):
        return fm
    end = text.find("---", 3)
    if end == -1:
        return fm
    for line in text[3:end].strip().split("\n"):
        line = line.strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        fm[key] = value
    return fm
```

Add the dataclass and enumerator after the `Partner` dataclass block (around line 117), so it sits with the other record types:

```python
@dataclass(frozen=True)
class CompetitorFiler:
    """A publicly traded competitor and its SEC filer identity."""
    slug: str         # competitor page slug, e.g. "acima"
    title: str        # display title, e.g. "Acima"
    parent: str       # SEC issuer / parent, e.g. "Upbound Group"
    ticker: str       # e.g. "UPBD"
    filer_slug: str   # slugify(parent), e.g. "upbound-group"


def parse_competitors(competitors_dir: Path | None = None) -> list[CompetitorFiler]:
    """Enumerate publicly traded competitors from pages/competitors/*.md.

    Skips pages whose `ticker` is empty or `private`, and pages with no
    `parent` (the SEC issuer). The filer slug is derived from `parent` so two
    brands under one issuer would resolve to the same filing tracker.
    """
    if competitors_dir is None:
        competitors_dir = PAGES / "competitors"
    out: list[CompetitorFiler] = []
    for f in sorted(competitors_dir.glob("*.md")):
        fm = parse_frontmatter(f.read_text(encoding="utf-8"))
        ticker = (fm.get("ticker") or "").strip()
        if not ticker or ticker.lower() == "private":
            continue
        parent = (fm.get("parent") or "").strip()
        if not parent:
            continue
        out.append(CompetitorFiler(
            slug=f.stem,
            title=(fm.get("title") or f.stem).strip(),
            parent=parent,
            ticker=ticker,
            filer_slug=slugify(parent),
        ))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_lib_competitors.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Sanity-check against the real pages**

Run: `python3 -c "import sys; sys.path.insert(0,'scripts'); from _lib import parse_competitors; [print(f.slug, '->', f.filer_slug, f.ticker) for f in parse_competitors()]"`
Expected: 5 lines — acima→upbound-group UPBD, affirm→affirm-holdings AFRM, american-first-finance→firstcash-holdings FCFS, klarna→klarna-group KLAR, progressive-leasing→prog-holdings PRG (koalafi absent).

- [ ] **Step 6: Commit**

```bash
git add scripts/_lib.py tests/__init__.py tests/test_lib_competitors.py
git commit -m "Add parse_competitors helper for SEC filer enumeration"
```

---

## Task 2: Pure EDGAR helpers in `sec_edgar.py`

The stdlib-only, network-free functions: CIK lookup, filing filter, filename builder, EDGAR URL, HTML→text, truncation, sidecar load/merge.

**Files:**
- Create: `scripts/sec_edgar.py`
- Test: `tests/test_sec_edgar.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_sec_edgar.py`:

```python
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from sec_edgar import (  # noqa: E402
    Filing, cik_from_ticker, filing_filename, filter_filings,
    edgar_doc_url, html_to_text, truncate_for_model,
    load_sidecar, merge_sidecar,
)

TICKER_MAP = {
    "0": {"cik_str": 1820953, "ticker": "AFRM", "title": "Affirm Holdings, Inc."},
    "1": {"cik_str": 933036, "ticker": "UPBD", "title": "Upbound Group, Inc."},
}


def test_cik_from_ticker_zero_pads():
    assert cik_from_ticker(TICKER_MAP, "upbd") == "0000933036"
    assert cik_from_ticker(TICKER_MAP, "AFRM") == "0001820953"
    assert cik_from_ticker(TICKER_MAP, "NOPE") is None


def test_filing_filename():
    f = Filing(form="10-K", filing_date="2026-02-15", report_date="2025-12-31",
               accession="0000933036-26-000012", primary_doc="upbd-20251231.htm",
               description="Form 10-K")
    assert filing_filename(f) == "2026-02-15_10-K_0000933036-26-000012.htm"


def test_filing_filename_sanitizes_slash_form():
    f = Filing(form="10-K/A", filing_date="2026-02-15", report_date="",
               accession="0000933036-26-000099", primary_doc="x.htm", description="")
    assert filing_filename(f) == "2026-02-15_10-K-A_0000933036-26-000099.htm"


def test_filter_filings_window_and_forms():
    today = dt.date(2026, 6, 15)
    recent = {
        "form":            ["10-K",       "8-K",        "DEF 14A",    "8-K"],
        "filingDate":      ["2026-02-15", "2026-05-01", "2026-04-30", "2024-01-01"],
        "reportDate":      ["2025-12-31", "",           "",           ""],
        "accessionNumber": ["a-1",        "a-2",        "a-3",        "a-4"],
        "primaryDocument": ["k.htm",      "e.htm",      "p.htm",      "old.htm"],
        "primaryDocDescription": ["10-K", "8-K", "Proxy", "8-K"],
    }
    got = filter_filings(recent, today)
    accs = [f.accession for f in got]
    assert accs == ["a-1", "a-2"]            # DEF 14A excluded; old 8-K out of window


def test_edgar_doc_url_strips_dashes_and_leading_zeros():
    url = edgar_doc_url("0000933036", "0000933036-26-000012", "upbd-20251231.htm")
    assert url == ("https://www.sec.gov/Archives/edgar/data/933036/"
                   "000093303626000012/upbd-20251231.htm")


def test_html_to_text_strips_tags_and_scripts():
    raw = b"<html><style>x{}</style><body><p>Net&nbsp;revenue was $1.2B.</p>" \
          b"<script>bad()</script></body></html>"
    txt = html_to_text(raw)
    assert "Net revenue was $1.2B." in txt
    assert "bad()" not in txt and "x{}" not in txt


def test_truncate_for_model():
    assert truncate_for_model("abcdef", max_chars=3) == "abc"
    assert truncate_for_model("ab", max_chars=10) == "ab"


def test_sidecar_merge_preserves_summary(tmp_path):
    path = tmp_path / "_filings.json"
    assert load_sidecar(path) == {}

    f1 = Filing("10-K", "2026-02-15", "2025-12-31", "a-1", "k.htm", "10-K")
    first = merge_sidecar(load_sidecar(path), "0000933036", [f1],
                          {"a-1": "2026-02-15_10-K_a-1.htm"})
    first["filings"]["a-1"]["summary"] = "Revenue up 8%."
    path.write_text(__import__("json").dumps(first), encoding="utf-8")

    # Re-fetch sees the same filing again — summary must survive the merge.
    second = merge_sidecar(load_sidecar(path), "0000933036", [f1],
                           {"a-1": "2026-02-15_10-K_a-1.htm"})
    assert second["cik"] == "0000933036"
    assert second["filings"]["a-1"]["summary"] == "Revenue up 8%."
    assert second["filings"]["a-1"]["local_file"] == "2026-02-15_10-K_a-1.htm"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_sec_edgar.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sec_edgar'`.

- [ ] **Step 3: Create `scripts/sec_edgar.py` with the pure helpers**

```python
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
    rdates = recent.get("reportDate", [])
    docs = recent.get("primaryDocument", [])
    descs = recent.get("primaryDocDescription", [])
    out: list[Filing] = []
    for i in range(n):
        form = recent["form"][i]
        if form not in forms_set:
            continue
        fdate = recent["filingDate"][i]
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
    """Crude HTML/XBRL → plain text for summarization input."""
    text = raw.decode("utf-8", "ignore") if isinstance(raw, bytes) else raw
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = _html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def truncate_for_model(text: str, max_chars: int = 120_000) -> str:
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_sec_edgar.py -v`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/sec_edgar.py tests/test_sec_edgar.py
git commit -m "Add pure SEC EDGAR helpers (CIK lookup, filing filter, sidecar)"
```

---

## Task 3: `EdgarClient` network layer in `sec_edgar.py`

Add the thin network client to `sec_edgar.py`: rate-limited GET, cached ticker map, submissions fetch, document download. Verified by a gated live smoke test (skipped when offline / `EDGAR_LIVE` unset) — no mock unit test.

**Files:**
- Modify: `scripts/sec_edgar.py`
- Test: `tests/test_sec_edgar.py` (append live smoke test)

- [ ] **Step 1: Append the live smoke test**

Add to the end of `tests/test_sec_edgar.py`:

```python
import os
import pytest


@pytest.mark.skipif(not os.environ.get("EDGAR_LIVE"),
                    reason="set EDGAR_LIVE=1 to run the live EDGAR smoke test")
def test_edgar_client_resolves_and_fetches(tmp_path):
    from sec_edgar import EdgarClient
    client = EdgarClient(cache_dir=tmp_path)
    tmap = client.ticker_map()
    cik = cik_from_ticker(tmap, "AFRM")
    assert cik and cik.isdigit() and len(cik) == 10
    subs = client.submissions(cik)
    assert "filings" in subs and "recent" in subs["filings"]
```

- [ ] **Step 2: Run test to verify it skips (no implementation yet, but import must hold)**

Run: `python3 -m pytest tests/test_sec_edgar.py -v`
Expected: previous 8 PASS; the new test reports SKIPPED — UNLESS it errors on `ImportError: cannot import name 'EdgarClient'`. That import error is the failing state we now fix.

- [ ] **Step 3: Append `EdgarClient` to `scripts/sec_edgar.py`**

```python
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
                self._ticker_map = json.loads(cache.read_text(encoding="utf-8"))
                return self._ticker_map
        data = self._get(TICKER_MAP_URL)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(data)
        self._ticker_map = json.loads(data)
        return self._ticker_map

    def submissions(self, cik10: str) -> dict:
        return json.loads(self._get(SUBMISSIONS_URL.format(cik10=cik10)))

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
```

- [ ] **Step 4: Run the live smoke test explicitly**

Run: `EDGAR_LIVE=1 python3 -m pytest tests/test_sec_edgar.py::test_edgar_client_resolves_and_fetches -v`
Expected: PASS (real network). If offline, this is the only step that requires connectivity; re-run when online.

- [ ] **Step 5: Run the full suite (smoke test auto-skips)**

Run: `python3 -m pytest tests/ -v`
Expected: all prior tests PASS, smoke test SKIPPED.

- [ ] **Step 6: Commit**

```bash
git add scripts/sec_edgar.py tests/test_sec_edgar.py
git commit -m "Add rate-limited EdgarClient (ticker cache, submissions, download)"
```

---

## Task 4: Tracker-page rendering in `refresh_sec_filings.py`

Pure rendering functions: a per-filer tracker page and the index roll-up. No network/API — testable in isolation.

**Files:**
- Create: `scripts/refresh_sec_filings.py` (rendering functions first; `main` added in Task 6)
- Test: `tests/test_render_pages.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_render_pages.py`:

```python
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from _lib import CompetitorFiler  # noqa: E402
from refresh_sec_filings import render_filer_page, render_index  # noqa: E402

FILER = CompetitorFiler(slug="acima", title="Acima", parent="Upbound Group",
                        ticker="UPBD", filer_slug="upbound-group")
TODAY = dt.date(2026, 6, 15)
SIDECAR = {
    "cik": "0000933036",
    "filings": {
        "0000933036-26-000012": {
            "form": "10-K", "filing_date": "2026-02-15", "report_date": "2025-12-31",
            "accession": "0000933036-26-000012", "primary_doc": "upbd-20251231.htm",
            "description": "Form 10-K",
            "local_file": "2026-02-15_10-K_0000933036-26-000012.htm",
            "summary": "#### Key financials\n- Revenue $4.3B, up 8%.",
        },
        "0000933036-26-000045": {
            "form": "8-K", "filing_date": "2026-05-01", "report_date": "",
            "accession": "0000933036-26-000045", "primary_doc": "e.htm",
            "description": "Form 8-K", "local_file": "", "summary": "",
        },
    },
}


def test_render_filer_page_table_and_summary():
    fm, body = render_filer_page(FILER, SIDECAR, TODAY)
    assert fm["type"] == "sec-filing"
    assert fm["competitor"] == "[[acima]]"
    assert fm["ticker"] == "UPBD"
    assert fm["count"] == 2
    # Newest filing first
    assert body.index("2026-05-01") < body.index("2026-02-15")
    # EDGAR link present for the 10-K
    assert ("https://www.sec.gov/Archives/edgar/data/933036/"
            "000093303626000012/upbd-20251231.htm") in body
    # Local doc link only for the downloaded filing
    assert "../../sec-filings/upbound-group/2026-02-15_10-K_0000933036-26-000012.htm" in body
    # Summary block rendered
    assert "## Filing summaries" in body
    assert "Revenue $4.3B, up 8%." in body


def test_render_filer_page_empty():
    fm, body = render_filer_page(FILER, {"cik": "0000933036", "filings": {}}, TODAY)
    assert fm["count"] == 0
    assert "No filings in the last 24 months" in body


def test_render_index_lists_filers():
    fm, body = render_index([(FILER, SIDECAR)], TODAY)
    assert fm["type"] == "sec-filing"
    assert fm["title"].startswith("SEC Filings")
    assert "[[upbound-group]]" in body or "Upbound Group" in body
    assert "UPBD" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_render_pages.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'refresh_sec_filings'`.

- [ ] **Step 3: Create `scripts/refresh_sec_filings.py` with the rendering functions**

```python
#!/usr/bin/env python3
"""Pull SEC filings for public competitors, store docs under sec-filings/,
render tracker pages under pages/sec-filings/, and rebuild the wiki.

Usage:
    python scripts/refresh_sec_filings.py --use-anthropic-api   # download + summarize
    python scripts/refresh_sec_filings.py --existing-only        # offline re-render
    python scripts/refresh_sec_filings.py --use-anthropic-api --dry-run
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import (  # noqa: E402
    PAGES, SEC_FILINGS_ROOT, WIKI_ROOT, CompetitorFiler, parse_competitors,
    write_page,
)
import sec_edgar as edgar  # noqa: E402


def _rows_newest_first(sidecar: dict) -> list[dict]:
    rows = list(sidecar.get("filings", {}).values())
    return sorted(rows, key=lambda r: r.get("filing_date", ""), reverse=True)


def render_filer_page(filer: CompetitorFiler, sidecar: dict,
                      today: dt.date) -> tuple[dict, str]:
    """Render a per-filer SEC tracker page (frontmatter, body)."""
    rows = _rows_newest_first(sidecar)
    cik = sidecar.get("cik", "")
    fm = {
        "title": f"{filer.parent} — SEC Filings",
        "type": "sec-filing",
        "competitor": f"[[{filer.slug}]]",
        "parent": filer.parent,
        "ticker": filer.ticker,
        "count": len(rows),
        "created": today.isoformat(),
        "updated": today.isoformat(),
    }
    parts = [
        f"# {filer.parent} — SEC Filings",
        "",
        f"_Updated: {today:%B %-d, %Y}_  ·  Filer for [[{filer.slug}]] "
        f"({filer.ticker})",
        "",
    ]
    if not rows:
        parts += ["_No filings in the last 24 months._", ""]
        return fm, "\n".join(parts)

    parts += [
        "## Filings",
        "",
        "| Form | Filed | Period | Document | Local |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        if cik and r.get("primary_doc"):
            url = edgar.edgar_doc_url(cik, r["accession"], r["primary_doc"])
            doc = f"[EDGAR]({url})"
        else:
            doc = "—"
        if r.get("local_file"):
            local = f"[file](../../sec-filings/{filer.filer_slug}/{r['local_file']})"
        else:
            local = "—"
        period = r.get("report_date") or "—"
        parts.append(f"| {r['form']} | {r['filing_date']} | {period} | {doc} | {local} |")
    parts.append("")

    summarized = [r for r in rows if r.get("summary")]
    if summarized:
        parts += ["## Filing summaries", ""]
        for r in summarized:
            parts += [f"### {r['form']} — {r['filing_date']}", "", r["summary"], ""]
    return fm, "\n".join(parts)


def render_index(filer_sidecars: list[tuple[CompetitorFiler, dict]],
                 today: dt.date) -> tuple[dict, str]:
    """Render the SEC filings index roll-up page."""
    total = sum(len(s.get("filings", {})) for _, s in filer_sidecars)
    fm = {
        "title": "SEC Filings — Tracker Index",
        "type": "sec-filing",
        "count": total,
        "created": today.isoformat(),
        "updated": today.isoformat(),
    }
    parts = [
        "# SEC Filings — Tracker Index",
        "",
        f"_Updated: {today:%B %-d, %Y}_  ·  **{total}** filings tracked across "
        f"**{len(filer_sidecars)}** public competitors.",
        "",
        "| Filer | Ticker | Competitor | Filings | Latest |",
        "| --- | --- | --- | --- | --- |",
    ]
    for filer, sidecar in sorted(filer_sidecars, key=lambda x: x[0].parent.lower()):
        rows = _rows_newest_first(sidecar)
        latest = rows[0]["filing_date"] if rows else "—"
        parts.append(
            f"| [[{filer.filer_slug}]] | {filer.ticker} | [[{filer.slug}]] | "
            f"{len(rows)} | {latest} |"
        )
    parts.append("")
    return fm, "\n".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_render_pages.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/refresh_sec_filings.py tests/test_render_pages.py
git commit -m "Add SEC tracker page + index rendering"
```

---

## Task 5: AI summary function in `refresh_sec_filings.py`

Add the Claude summarization function. The text-shaping is already covered by `html_to_text`/`truncate_for_model` (Task 2); this step wires the API call, following `refresh_industry_reports.py`'s model and message shape.

**Files:**
- Modify: `scripts/refresh_sec_filings.py`

- [ ] **Step 1: Add the summarizer to `scripts/refresh_sec_filings.py`**

Insert after the imports (before `_rows_newest_first`):

```python
SUMMARY_SYSTEM = (
    "You are an equity analyst summarizing an SEC filing for Snap Finance, a "
    "point-of-sale financing / lease-to-own company that tracks competitors. "
    "Be concise, factual, and specific with numbers and dates."
)


def summarize_filing(client, form: str, filing_date: str, text: str,
                     model: str = "claude-sonnet-4-6") -> str:
    """Summarize one filing's text via the Anthropic API. Returns markdown."""
    prompt = (
        f"Summarize this {form} filed {filing_date}. Use these level-4 headings "
        "EXACTLY and in this order:\n"
        "#### Key financials\n"
        "#### Segment & competitive notes\n"
        "#### Risk-factor changes\n"
        "#### Material events\n\n"
        "Give 2-4 bullet points under each heading, with specific numbers and "
        "dates. If a section has nothing material, write '- None noted.'\n\n"
        f"FILING TEXT (may be truncated):\n{text}"
    )
    resp = client.messages.create(
        model=model,
        max_tokens=1200,
        system=SUMMARY_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return "\n\n".join(
        b.text for b in resp.content if getattr(b, "type", "") == "text"
    ).strip()
```

- [ ] **Step 2: Verify it imports cleanly**

Run: `python3 -c "import sys; sys.path.insert(0,'scripts'); import refresh_sec_filings as r; print('summarize_filing' in dir(r))"`
Expected: `True`.

- [ ] **Step 3: Run the full suite (no behavior change to pure tests)**

Run: `python3 -m pytest tests/ -v`
Expected: all PASS / smoke SKIPPED.

- [ ] **Step 4: Commit**

```bash
git add scripts/refresh_sec_filings.py
git commit -m "Add Claude filing-summary function"
```

---

## Task 6: Orchestrator `main()` in `refresh_sec_filings.py`

Wire flags, the per-filer fetch/download/summarize loop, page writes, sidecar persistence, and the wiki rebuild — mirroring `refresh_industry_reports.py:main`.

**Files:**
- Modify: `scripts/refresh_sec_filings.py`

- [ ] **Step 1: Add `_load_env`, the per-filer processing, and `main` to the end of the file**

```python
def _load_env() -> None:
    """Load .env into os.environ (same pattern as refresh_industry_reports.py)."""
    env_file = WIKI_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def _process_filer(filer: CompetitorFiler, client, today: dt.date,
                   *, use_api: bool, dry_run: bool) -> dict:
    """Network path: resolve CIK, fetch + filter filings, download docs, and
    (optionally) summarize. Returns the updated sidecar dict (also persisted
    to disk unless dry_run)."""
    edgar_client = _process_filer.client  # set by main()
    tmap = edgar_client.ticker_map()
    cik = edgar.cik_from_ticker(tmap, filer.ticker)
    if not cik:
        print(f"  ! {filer.parent}: ticker {filer.ticker} not found in EDGAR — skipping")
        return {}

    subs = edgar_client.submissions(cik)
    recent = subs.get("filings", {}).get("recent", {})
    filings = edgar.filter_filings(recent, today)
    print(f"  · {filer.parent} ({filer.ticker}): {len(filings)} in-scope filings", end=" ")

    filer_dir = SEC_FILINGS_ROOT / filer.filer_slug
    sidecar_path = filer_dir / "_filings.json"
    sidecar = edgar.load_sidecar(sidecar_path)
    prior_summaries = {a: r.get("summary", "")
                       for a, r in sidecar.get("filings", {}).items()}

    local_names: dict[str, str] = {}
    for f in filings:
        name = edgar.filing_filename(f)
        dest = filer_dir / name
        if dry_run:
            local_names[f.accession] = name if dest.exists() else ""
            continue
        try:
            edgar_client.download(cik, f, dest)
            local_names[f.accession] = name
        except Exception as e:  # one bad doc must not abort the filer
            print(f"\n    ! download failed for {f.accession}: {e}", end="")
            local_names[f.accession] = ""

    sidecar = edgar.merge_sidecar(sidecar, cik, filings, local_names)

    if use_api and client and not dry_run:
        new_count = 0
        for f in filings:
            if prior_summaries.get(f.accession):
                continue  # already summarized
            local = sidecar["filings"][f.accession].get("local_file")
            if not local:
                continue
            try:
                raw = (filer_dir / local).read_bytes()
                text = edgar.truncate_for_model(edgar.html_to_text(raw))
                summary = summarize_filing(client, f.form, f.filing_date, text)
                sidecar["filings"][f.accession]["summary"] = summary
                new_count += 1
            except Exception as e:
                print(f"\n    ! summary failed for {f.accession}: {e}", end="")
        print(f"({new_count} new summaries)", end=" ")

    if not dry_run:
        sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        sidecar_path.write_text(__import__("json").dumps(sidecar, indent=2),
                                encoding="utf-8")
    print("✓")
    return sidecar


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--use-anthropic-api", action="store_true",
                    help="Download docs and generate/refresh AI summaries")
    ap.add_argument("--existing-only", action="store_true",
                    help="Re-render tracker pages from local sidecars (offline)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Report what would happen without writing")
    args = ap.parse_args(argv)

    if not args.use_anthropic_api and not args.existing_only:
        ap.error("provide --use-anthropic-api or --existing-only")

    today = dt.date.today()
    filers = parse_competitors()
    print(f"SEC filings refresh for {len(filers)} public competitors…")

    client = None
    if args.use_anthropic_api:
        _load_env()
        try:
            from anthropic import Anthropic
        except ImportError:
            print("ERROR: pip install anthropic", file=sys.stderr)
            return 2
        client = Anthropic()

    filer_sidecars: list[tuple[CompetitorFiler, dict]] = []

    if args.existing_only:
        # Offline: render from whatever sidecars exist on disk.
        for filer in filers:
            sidecar = edgar.load_sidecar(
                SEC_FILINGS_ROOT / filer.filer_slug / "_filings.json")
            filer_sidecars.append((filer, sidecar))
    else:
        _process_filer.client = edgar.EdgarClient(cache_dir=SEC_FILINGS_ROOT)
        for filer in filers:
            try:
                sidecar = _process_filer(filer, client, today,
                                         use_api=args.use_anthropic_api,
                                         dry_run=args.dry_run)
            except Exception as e:  # one bad filer must not abort the run
                print(f"  ! {filer.parent}: {e} — skipping")
                sidecar = edgar.load_sidecar(
                    SEC_FILINGS_ROOT / filer.filer_slug / "_filings.json")
            filer_sidecars.append((filer, sidecar))

    if args.dry_run:
        print("· dry-run: no pages written, no wiki rebuild")
        return 0

    out_dir = PAGES / "sec-filings"
    for filer, sidecar in filer_sidecars:
        fm, body = render_filer_page(filer, sidecar, today)
        write_page(out_dir / f"{filer.filer_slug}.md", fm, body, overwrite=True)
    fm, body = render_index(filer_sidecars, today)
    write_page(out_dir / "index.md", fm, body, overwrite=True)
    print(f"  · wrote {len(filer_sidecars)} tracker pages + index")

    print("  · rebuilding wiki…")
    subprocess.run(["python3", "build_wiki.py", "--no-embed-key"],
                   cwd=WIKI_ROOT, check=True)
    print("  ✓ SEC filings refresh complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

> Note: `_process_filer.client` is a function attribute set in `main` so the
> single rate-limited `EdgarClient` is shared across filers without threading it
> through every call. `__import__("json")` is used locally to avoid adding a
> top-level import solely for one `dumps`.

- [ ] **Step 2: Run a dry-run against live EDGAR**

Run: `cd /Users/jlannoy/Documents/GitHub/partner-wiki && python3 scripts/refresh_sec_filings.py --use-anthropic-api --dry-run`
Expected: one line per public competitor showing in-scope filing counts; ends with `dry-run: no pages written`. (Requires network; if offline, re-run when connected.)

- [ ] **Step 3: Run a real refresh**

Run: `python3 scripts/refresh_sec_filings.py --use-anthropic-api`
Expected: per-filer downloads + `(N new summaries)`, then `wrote 5 tracker pages + index`, then a wiki build line `Pages: …`. Verify `ls sec-filings/*/` shows downloaded docs + `_filings.json`, and `ls pages/sec-filings/` shows `index.md` + 5 filer pages.

- [ ] **Step 4: Verify idempotency**

Run: `python3 scripts/refresh_sec_filings.py --use-anthropic-api`
Expected: `0 new summaries` for every filer and no new files in `sec-filings/` (the second run downloads nothing).

- [ ] **Step 5: Verify offline re-render**

Run: `python3 scripts/refresh_sec_filings.py --existing-only`
Expected: tracker pages re-written from sidecars with no network calls; wiki rebuilds.

- [ ] **Step 6: Commit**

```bash
git add scripts/refresh_sec_filings.py
git commit -m "Add SEC filings orchestrator (fetch, download, summarize, render)"
```

---

## Task 7: Register the new page directory in `build_wiki.py`

**Files:**
- Modify: `build_wiki.py:54-63`

- [ ] **Step 1: Add the directory to `PAGE_DIRS`**

In `build_wiki.py`, change the `PAGE_DIRS` list to append the SEC dir (after the `opportunities` entry, line 62):

```python
PAGE_DIRS = [
    ("pages/editions", "edition"),
    ("pages/events", "event"),
    ("pages/partners", "partner"),
    ("pages/competitors", "competitor"),
    ("pages/saes", "sae"),
    ("pages/sources", "source"),
    ("pages/industries", "industry"),
    ("pages/opportunities", "opportunity-list"),
    ("pages/sec-filings", "sec-filing"),
]
```

- [ ] **Step 2: Rebuild and confirm the pages are collected**

Run: `cd /Users/jlannoy/Documents/GitHub/partner-wiki && python3 build_wiki.py --no-embed-key`
Expected: `Pages: N` (N increased by 6 vs. before this task) and `JSON valid: N pages parsed OK`.

- [ ] **Step 3: Confirm the new type made it into the built data**

Run: `grep -c '"type": "sec-filing"' pages/wiki.html`
Expected: `6` (5 filers + index).

- [ ] **Step 4: Commit**

```bash
git add build_wiki.py pages/wiki.html pages/sec-filings
git commit -m "Collect pages/sec-filings into the wiki build"
```

---

## Task 8: Competitor Watch tab in `wiki_app.js`

Add the SEC-filings data maps, a `CompetitorView` component joining each competitor to its tracker, the routing branch, the sidebar entry, and a command-palette action.

**Files:**
- Modify: `wiki_app.js` (data maps ~line 59; `TYPE_LABELS` ~line 87; new component before `Sidebar` ~line 755; `Sidebar` ~line 766; `App` switch ~line 1392; `CommandPalette` actions — see Step 5)

- [ ] **Step 1: Add the SEC-filings data maps**

In `wiki_app.js`, immediately after the `COMPETITOR_PAGES` definition (line 59), add:

```javascript
const SEC_FILING_PAGES = RAW_PAGES.filter(p => p.type === 'sec-filing');
// Join a competitor page slug -> its SEC tracker page via the tracker's
// `competitor: [[slug]]` frontmatter (set by render_filer_page).
const SEC_FILING_MAP = {};
SEC_FILING_PAGES.forEach(p => {
  const c = (p.competitor || '').replace(/\[\[|\]\]/g, '').trim();
  if (c) SEC_FILING_MAP[c] = p;
});
```

- [ ] **Step 2: Add the type label**

In the `TYPE_LABELS` object (line 87), add a `sec-filing` entry:

```javascript
const TYPE_LABELS = {
  edition: 'Edition', event: 'Event', partner: 'Partner',
  competitor: 'Competitor', sae: 'SAE', segment: 'Segment', source: 'Source',
  industry: 'Industry', 'sec-filing': 'SEC Filing',
  'opportunity-list': 'Opportunities', 'opportunity-index': 'Opportunities',
};
```

- [ ] **Step 3: Add the `CompetitorView` component**

Insert this function immediately before `function Sidebar(` (line 756):

```javascript
// ─── Competitor Watch View ───────────────────────────────────────────────────
function CompetitorView({ navigateTo }) {
  const cards = useMemo(() => COMPETITOR_PAGES.map(c => {
    const body = (c.content || '').replace(/^---[\s\S]*?---/, '');
    // Recent-move event slugs are wiki-links under "## Recent moves".
    const moveSlugs = (body.match(/\[\[([^\]]+)\]\]/g) || [])
      .map(m => m.replace(/\[\[|\]\]/g, '').trim())
      .filter(slug => PAGE_MAP[slug] && PAGE_MAP[slug].type === 'event');
    const moves = [...new Set(moveSlugs)]
      .map(slug => PAGE_MAP[slug])
      .sort((a, b) => (b.date || '').localeCompare(a.date || ''))
      .slice(0, 4);
    const tracker = SEC_FILING_MAP[c.slug] || null;
    return { c, moves, tracker, filings: tracker ? (parseInt(tracker.count, 10) || 0) : 0 };
  }), []);

  const totalFilings = cards.reduce((n, x) => n + x.filings, 0);

  return (
    <div className="main-content">
      <div className="page-header">
        <span className="page-type">Competitor Watch</span>
        <h1>Competitor Watch</h1>
        <div className="page-meta">
          <span><strong>{COMPETITOR_PAGES.length}</strong> competitors watched</span>
          <span><strong>{SEC_FILING_PAGES.filter(p => p.competitor).length}</strong> public filers</span>
          <span><strong>{totalFilings}</strong> SEC filings tracked</span>
        </div>
      </div>
      <div className="md-content">
        {cards.map(({ c, moves, tracker, filings }) => (
          <div key={c.slug} style={{ marginBottom: 28 }}>
            <hr className="section-divider" />
            <h2 style={{ display: 'inline-block', cursor: 'pointer', color: 'var(--accent)' }}
                onClick={() => navigateTo(c.slug)}>{c.title}</h2>
            <div className="page-meta" style={{ marginBottom: 10 }}>
              {c.parent && c.parent !== c.title && <span>Parent: {c.parent}</span>}
              {c.ticker && c.ticker !== 'private' && <span>Ticker: {c.ticker}</span>}
              {c.category && <span>{c.category.toUpperCase()}</span>}
            </div>

            {moves.length > 0 && (
              <div style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 6 }}>Recent moves</div>
                {moves.map(e => (
                  <div key={e.slug}
                       className={'industry-event' + (e.significance === 'high' ? ' event-high-impact' : '')}
                       onClick={() => navigateTo(e.slug)}>
                    <SignalChip sig={classifySignal(e)} />
                    <span className="industry-event-date">{e.date}</span>
                    <span className="industry-event-title">{e.title}</span>
                  </div>
                ))}
              </div>
            )}

            <div style={{ background: 'var(--soft)', border: '1px solid var(--line)',
                          borderRadius: 6, padding: '10px 14px', fontSize: 13 }}>
              {tracker ? (
                <span style={{ cursor: 'pointer', color: 'var(--accent)', fontWeight: 600 }}
                      onClick={() => navigateTo(tracker.slug)}>
                  View {filings} SEC filing{filings !== 1 ? 's' : ''} →
                </span>
              ) : (
                <span style={{ color: 'var(--muted)' }}>Private — no SEC filings tracked</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Add the sidebar entry and the routing branch**

In `Sidebar` (the "Views" section, after the `Trend Analysis` item at line 772), add:

```javascript
        <div className={'sidebar-item' + (activeView === 'competitors' ? ' active' : '')} onClick={() => setActiveView('competitors')}>
          <span>Competitor Watch</span>
          <span className="count-badge">{COMPETITOR_PAGES.length}</span>
        </div>
```

In `App`'s content switch (line 1390-1393), add a branch after the `trends` branch:

```javascript
  } else if (activeView === 'trends') {
    content = <TrendView />;
  } else if (activeView === 'competitors') {
    content = <CompetitorView navigateTo={(slug) => { setActiveView('page'); navigateTo(slug); }} />;
  } else if (activeView === 'industry') {
```

- [ ] **Step 5: Add a command-palette action**

In `CommandPalette`, the empty-query "Go to" actions are pushed at lines
1262-1264. Add a `competitors` action immediately after the `trends` line
(1263):

```javascript
      items.push({ action: 'edition', title: "Today's Edition", icon: 'edition' });
      items.push({ action: 'trends', title: 'Trend Analysis', icon: 'event' });
      items.push({ action: 'competitors', title: 'Competitor Watch', icon: 'event' });
      items.push({ action: 'ask', title: 'Ask Claude', icon: 'sae' });
```

The `choose` dispatch (line 1286, `else if (it.action) { setActiveView(it.action); }`)
already routes any `action` string to `setActiveView`, so no dispatch change is
needed.

- [ ] **Step 6: Rebuild and verify the bundle embeds the view**

Run: `cd /Users/jlannoy/Documents/GitHub/partner-wiki && python3 build_wiki.py --no-embed-key`
Expected: `JSON valid: N pages parsed OK`.

Run: `grep -c "CompetitorView" pages/wiki.html`
Expected: `>= 2` (definition + usage).

- [ ] **Step 7: Manual smoke test in a browser**

Open `pages/wiki.html` in a browser. Confirm: a **Competitor Watch** item appears under Views; clicking it lists all 6 competitors; each public competitor shows a "View N SEC filings →" link that navigates to the tracker page (table + summaries); Koalafi shows "Private — no SEC filings tracked"; `Cmd/Ctrl-K` → "Competitor Watch" opens the same view.

- [ ] **Step 8: Commit**

```bash
git add wiki_app.js pages/wiki.html
git commit -m "Add standalone Competitor Watch tab joining competitors to SEC filings"
```

---

## Task 9: Weekly automation hook in `refresh_and_push.sh`

Add `pages/sec-filings` and `sec-filings` to the git-add allowlist and a non-fatal Monday hook.

**Files:**
- Modify: `scripts/refresh_and_push.sh` (after line 125; lines 139-142)

- [ ] **Step 1: Add the non-fatal Monday hook**

In `scripts/refresh_and_push.sh`, after the closing `fi` of the Monday industry-research block (line 125) and before the `# ---------- 7. ...` API-key check (line 127), insert:

```bash
# ---------- 6c. Weekly (Monday) SEC filings refresh ----------
# Pull the latest SEC filings for public competitors and regenerate the
# tracker pages + AI summaries. Like the industry refresh, this MUST NOT abort
# the wrapper on failure — an EDGAR outage or Anthropic rate limit should never
# wipe out the weekly stage/commit/push. Filings already on disk survive a
# failed run, and --existing-only would re-render them next cycle.
if [ "$(date +%u)" = "1" ]; then
  echo "· Monday: running weekly SEC filings refresh"
  python3 scripts/refresh_sec_filings.py --use-anthropic-api \
    || echo "✗ Monday SEC filings refresh failed (non-fatal — commit unaffected)"
fi
```

- [ ] **Step 2: Add the new paths to the git-add allowlist**

Change the `git add` block (lines 139-142) to include the two new paths:

```bash
git add pages/wiki.html pages/index.md \
        pages/editions pages/events pages/sources \
        pages/partners pages/competitors \
        pages/saes pages/industries pages/opportunities \
        pages/sec-filings sec-filings
```

- [ ] **Step 3: Syntax-check the script**

Run: `bash -n scripts/refresh_and_push.sh`
Expected: no output (exit 0 — script parses).

- [ ] **Step 4: Commit**

```bash
git add scripts/refresh_and_push.sh
git commit -m "Hook SEC filings refresh into the weekly Monday run"
```

---

## Task 10: Documentation + final verification

**Files:**
- Modify: `AGENT_RUNBOOK.md` (add a short SEC-filings section); `requirements.txt` (note only — no new dep)

- [ ] **Step 1: Document the new pipeline in `AGENT_RUNBOOK.md`**

Add a section describing: the `refresh_sec_filings.py` flags; that raw docs live under `sec-filings/` (committed); the `_filings.json` sidecar is the offline source of truth; EDGAR needs no key but uses a contact User-Agent; and the Monday hook is non-fatal. Match the runbook's existing heading style (open the file and mirror a nearby section's format).

- [ ] **Step 2: Confirm no new third-party dependency was introduced**

Run: `grep -nE "^import |^from " scripts/sec_edgar.py scripts/refresh_sec_filings.py | grep -vE "from __future__|_lib|sec_edgar|argparse|datetime|json|os|re|subprocess|sys|time|urllib|html|pathlib|dataclasses"`
Expected: only the lazy `from anthropic import Anthropic` inside `main` (already in requirements.txt). No `requests`. `requirements.txt` needs no change.

- [ ] **Step 3: Run the full test suite**

Run: `cd /Users/jlannoy/Documents/GitHub/partner-wiki && python3 -m pytest tests/ -v`
Expected: all unit tests PASS; the live EDGAR smoke test SKIPPED (unless `EDGAR_LIVE=1`).

- [ ] **Step 4: Confirm a clean working tree after a real run + build**

Run: `python3 scripts/refresh_sec_filings.py --existing-only && git status --porcelain`
Expected: only expected, intended changes appear (tracker pages, wiki.html). No stray `.tmp` files.

- [ ] **Step 5: Commit**

```bash
git add AGENT_RUNBOOK.md
git commit -m "Document the SEC filings tracker pipeline"
```

---

## Verification checklist (whole feature)

- [ ] `parse_competitors()` returns the 5 public filers and skips Koalafi.
- [ ] `refresh_sec_filings.py --use-anthropic-api` downloads docs to `sec-filings/<filer>/`, writes `_filings.json`, and generates summaries.
- [ ] A second run is idempotent (0 new downloads, 0 new summaries).
- [ ] `--existing-only` re-renders fully offline.
- [ ] `pages/sec-filings/` (index + 5 filer pages) render in the built wiki.
- [ ] The Competitor Watch tab is reachable from the sidebar and `Cmd/Ctrl-K`, lists all competitors, and deep-links resolve to tracker pages.
- [ ] `bash -n scripts/refresh_and_push.sh` passes; the Monday hook is non-fatal; allowlist includes the new paths.
- [ ] No new dependency in `requirements.txt`.
