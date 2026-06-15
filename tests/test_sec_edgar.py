import datetime as dt
import os
import sys
from pathlib import Path

import pytest

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
    assert accs == ["a-1", "a-2"]            # DEF 14A excluded; old 8-K out of 24mo window


def test_filter_filings_includes_boundary_day():
    today = dt.date(2026, 6, 15)
    recent = {
        "form":            ["8-K"],
        "filingDate":      ["2024-06-15"],   # exactly today - 730 days; d < cutoff is False
        "reportDate":      [""],
        "accessionNumber": ["b-1"],
        "primaryDocument": ["e.htm"],
        "primaryDocDescription": ["8-K"],
    }
    assert [f.accession for f in filter_filings(recent, today)] == ["b-1"]


def test_filter_filings_survives_missing_form_column():
    today = dt.date(2026, 6, 15)
    recent = {"accessionNumber": ["a-1"], "filingDate": ["2026-02-15"]}  # no "form"
    assert filter_filings(recent, today) == []


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
