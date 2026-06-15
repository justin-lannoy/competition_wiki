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
    assert "[[upbound-group]]" in body    # filer wiki-link
    assert "[[acima]]" in body            # competitor wiki-link
    assert "UPBD" in body
