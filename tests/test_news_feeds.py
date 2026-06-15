import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import news_feeds as nf  # noqa: E402

GOOGLE_RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item>
    <title>Affirm expands BNPL to new merchants - Reuters</title>
    <link>https://www.reuters.com/affirm-expands</link>
    <pubDate>Wed, 10 Jun 2026 14:00:00 GMT</pubDate>
    <description>&lt;a href="x"&gt;Affirm expands&lt;/a&gt; into furniture retail.</description>
    <source url="https://www.reuters.com">Reuters</source>
  </item>
  <item>
    <title>Affirm Q3 earnings beat - CNBC</title>
    <link>https://www.cnbc.com/affirm-q3</link>
    <pubDate>Mon, 01 Jun 2026 09:00:00 GMT</pubDate>
    <source url="https://www.cnbc.com">CNBC</source>
  </item>
</channel></rss>"""

XXE = """<?xml version="1.0"?>
<!DOCTYPE rss [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<rss version="2.0"><channel><item><title>&xxe;</title><link>http://x</link></item></channel></rss>"""


def test_parse_rss_extracts_items_and_source():
    items = nf.parse_rss(GOOGLE_RSS)
    assert len(items) == 2
    first = items[0]
    assert first.title == "Affirm expands BNPL to new merchants"  # source suffix stripped
    assert first.source == "Reuters"
    assert first.published == "2026-06-10"
    assert first.url == "https://www.reuters.com/affirm-expands"
    assert "furniture retail" in first.snippet


def test_parse_rss_rejects_doctype_entities():
    # XXE / billion-laughs payloads (any DOCTYPE) are refused outright.
    assert nf.parse_rss(XXE) == []


def test_parse_rss_malformed_returns_empty():
    assert nf.parse_rss(b"not xml at all") == []


def test_news_query_ors_in_distinct_parent():
    assert nf.news_query("Acima", "Upbound Group") == '"Acima" OR "Upbound Group"'
    # parent contained in name, or parenthetical noise -> single quoted term
    assert nf.news_query("Affirm Holdings", "Affirm Holdings") == '"Affirm Holdings"'
    assert nf.news_query("Koalafi", "Koalafi (private)") == '"Koalafi"'


def test_filter_recent_and_dedupe():
    today = dt.date(2026, 6, 15)
    items = [
        nf.NewsItem("a", "http://x/1", "S", "2026-06-10", "google-news"),
        nf.NewsItem("b", "http://x/2", "S", "2026-01-01", "google-news"),  # too old
        nf.NewsItem("a-dup", "http://x/1", "S", "2026-06-11", "google-news"),  # dup url
    ]
    recent = nf.filter_recent(items, today, days=60)
    assert {i.url for i in recent} == {"http://x/1"}  # old dropped (note dup still both <60d? no)
    # rebuild with both recent to test dedupe independently
    recent2 = nf.dedupe([items[0], items[2]])
    assert len(recent2) == 1


def test_merge_sidecar_preserves_summary():
    existing = {"slug": "affirm", "items": {
        nf.item_id(nf.NewsItem("a", "http://x/1", "S", "2026-06-10", "google-news")): {
            "title": "a", "url": "http://x/1", "source": "S",
            "published": "2026-06-10", "feed": "google-news",
            "snippet": "", "summary": "PRIOR SUMMARY",
        }
    }}
    fresh = [nf.NewsItem("a", "http://x/1", "S", "2026-06-10", "google-news")]
    merged = nf.merge_sidecar(existing, "affirm", fresh)
    iid = nf.item_id(fresh[0])
    assert merged["items"][iid]["summary"] == "PRIOR SUMMARY"  # not clobbered
