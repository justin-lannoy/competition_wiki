#!/usr/bin/env python3
"""News + PR feed client and pure helpers for the competitor news tracker.

Stdlib only (mirrors sec_edgar.py): the network surface is a tiny rate-limited
`NewsClient`; everything else is pure, unit-testable data-shaping. Coverage comes
from Google News RSS (no API key) keyed on the competitor + parent name; official
press releases come from any per-competitor PR/IR RSS feed listed in the registry.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html as _html
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path

NEWS_UA = "Snap Finance competition_wiki refresh_news.py jlannoy@snapfinance.com"
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
MIN_INTERVAL = 0.5   # seconds between requests — gentle with public feeds


@dataclass(frozen=True)
class NewsItem:
    title: str
    url: str
    source: str
    published: str    # ISO "YYYY-MM-DD" ("" if unparseable)
    feed: str         # "google-news" | "pr"
    snippet: str = "" # short RSS description text (summary input)
    summary: str = "" # AI-generated brief (filled by refresh_news)


# ---------------------------------------------------------------------------
# Query + URL building
# ---------------------------------------------------------------------------

def _strip_parentheticals(s: str) -> str:
    """Drop trailing notes like '(private)' or '(AFF)' from a display name."""
    return re.sub(r"\s*\([^)]*\)", "", s or "").strip()


def news_query(title: str, parent: str = "") -> str:
    """Build a Google News query from competitor + parent display names.

    Quotes the brand; OR-s in the parent when it's a distinct issuer name so
    coverage filed under the parent (e.g. Upbound for Acima) is captured too.
    """
    name = _strip_parentheticals(title)
    p = _strip_parentheticals(parent)
    if p and p.lower() not in name.lower():
        return f'"{name}" OR "{p}"'
    return f'"{name}"'


def google_news_url(query: str, when_days: int = 60) -> str:
    q = f"{query} when:{when_days}d"
    return GOOGLE_NEWS_RSS.format(q=urllib.parse.quote(q))


# ---------------------------------------------------------------------------
# RSS parsing (pure)
# ---------------------------------------------------------------------------

def _rfc822_to_iso(s: str) -> str:
    try:
        return parsedate_to_datetime(s).date().isoformat()
    except (TypeError, ValueError, IndexError, OverflowError):
        return ""


def _host(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.replace("www.", "")
    except ValueError:
        return ""


def _strip_tags(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", _html.unescape(s or ""))).strip()


def _strip_source_suffix(title: str, source: str) -> str:
    """Google News titles read 'Headline - Source'; drop the source suffix."""
    if source and title.endswith(f" - {source}"):
        return title[: -(len(source) + 3)].strip()
    return title.strip()


def parse_rss(xml_bytes: "bytes | str", *, feed: str = "google-news") -> list[NewsItem]:
    """Parse an RSS/Atom feed into NewsItems. Returns [] on malformed XML.

    Handles RSS 2.0 `<item>` (Google News, most PR wires) and Atom `<entry>`.

    Security: the stdlib ElementTree/expat parser is vulnerable to entity-based
    attacks (XXE, billion-laughs). The project is stdlib-only (no `defusedxml`),
    so we mitigate by refusing any feed that declares a DOCTYPE — both attacks
    require a DTD/entity definition, and legitimate RSS/Atom never carries one.
    """
    raw = xml_bytes if isinstance(xml_bytes, (bytes, bytearray)) else xml_bytes.encode("utf-8")
    # Refuse any DOCTYPE/entity declaration (XXE / billion-laughs) — same window
    # for both checks. Legitimate RSS/Atom never carries one.
    head = raw[:4096].lower()
    if b"<!doctype" in head or b"<!entity" in head:
        return []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []

    def _local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]  # strip XML namespace

    out: list[NewsItem] = []
    for node in root.iter():
        if _local(node.tag) not in ("item", "entry"):
            continue
        title = link = source = pub = desc = ""
        for child in node:
            t = _local(child.tag)
            if t == "title":
                title = (child.text or "").strip()
            elif t == "link":
                link = (child.text or "").strip() or child.get("href", "").strip()
            elif t == "source":
                source = (child.text or "").strip()
            elif t in ("pubDate", "published", "updated"):
                pub = pub or (child.text or "").strip()
            elif t in ("description", "summary", "content"):
                desc = desc or (child.text or "")
        if not title or not link:
            continue
        title = _html.unescape(_strip_source_suffix(title, source))
        out.append(NewsItem(
            title=title, url=link, source=source or _host(link),
            published=_rfc822_to_iso(pub), feed=feed, snippet=_strip_tags(desc)[:500],
        ))
    return out


# ---------------------------------------------------------------------------
# Selection + de-duplication (pure)
# ---------------------------------------------------------------------------

# Low-signal aggregators and insider-filing/stock-rating noise that dominate a
# Google-News query on a public ticker. Filtered before items reach a sidecar.
DENY_SOURCES = (
    "gurufocus", "stocktitan", "stock titan", "simplywall", "chartmill", "zacks",
    "tipranks", "marketbeat", "insider monkey", "insidermonkey", "kalkine",
    "247 wall st", "247wallst", "quiver quantitative", "defense world",
    "etf daily news", "the globe and mail", "barchart", "stockstory",
)
# Title patterns marking insider-filing / stock-rating noise, matched on WORD
# BOUNDARIES — a bare "vest" substring would wrongly drop "investment" /
# "investor" / "harvest", and the prune re-applies every run (permanent loss).
_DENY_TITLE_RE = re.compile(
    r"\b(?:rsu|vest(?:ed|ing|s)?|13f|p/e ratio|options trading|shares withheld|"
    r"tax withholding|gf value|zacks rank|stocks? to buy|good stock|best stock|"
    r"momentum stock|price target|should you buy|is it a buy|hold or sell)\b",
    re.I)


def is_noise(item: NewsItem) -> bool:
    """True for low-signal stock-blog / insider-filing items (deny-listed)."""
    src = (item.source or "").lower()
    if any(d in src for d in DENY_SOURCES):
        return True
    return bool(_DENY_TITLE_RE.search(item.title or ""))


def parse_significance(summary: str) -> str:
    """Extract the significance tag from an AI summary. Uses the LAST match —
    the structured 'Significance: …' tag line is appended at the end, so this
    ignores the word 'significance' appearing earlier in the prose body."""
    matches = re.findall(r"significance:\s*(low|medium|high)", summary or "", re.I)
    return matches[-1].lower() if matches else ""


def item_id(item: NewsItem) -> str:
    """Stable id from the URL (falls back to title) for idempotent sidecars."""
    key = item.url or item.title
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def filter_recent(items: list[NewsItem], today: dt.date, *, days: int = 60) -> list[NewsItem]:
    cutoff = today - dt.timedelta(days=days)
    out: list[NewsItem] = []
    for it in items:
        if not it.published:
            out.append(it)            # keep undated items (rare); don't lose them
            continue
        try:
            d = dt.date.fromisoformat(it.published)
        except ValueError:
            out.append(it)
            continue
        if d >= cutoff:
            out.append(it)
    return out


def dedupe(items: list[NewsItem]) -> list[NewsItem]:
    """Drop duplicate URLs, keeping first occurrence (preserves order)."""
    seen: set[str] = set()
    out: list[NewsItem] = []
    for it in items:
        k = item_id(it)
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


def sort_newest_first(items: list[NewsItem]) -> list[NewsItem]:
    return sorted(items, key=lambda it: it.published or "", reverse=True)


# ---------------------------------------------------------------------------
# Sidecar persistence (idempotent; preserves AI summaries across runs)
# ---------------------------------------------------------------------------

def load_sidecar(path: Path) -> dict:
    """Read a per-competitor _news.json sidecar; {} if missing or corrupt."""
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def merge_sidecar(existing: dict, slug: str, items: list[NewsItem]) -> dict:
    """Merge freshly fetched items into a sidecar, keyed by item id.

    Preserves any prior `summary` so re-runs don't re-summarize. Returns a new
    dict; does not mutate `existing`."""
    prev = existing.get("items", {})
    if not isinstance(prev, dict):
        prev = {}
    by_id: dict[str, dict] = dict(prev)
    for it in items:
        iid = item_id(it)
        old = by_id.get(iid, {})
        # Prefer freshly-parsed values but fall back to prior non-empty ones —
        # Google News sometimes returns a blank <source>/pubDate on one fetch.
        by_id[iid] = {
            "title": it.title or old.get("title", ""),
            "url": it.url or old.get("url", ""),
            "source": it.source or old.get("source", ""),
            "published": it.published or old.get("published", ""),
            "feed": it.feed or old.get("feed", ""),
            "snippet": it.snippet or old.get("snippet", ""),
            "summary": old.get("summary", "") or it.summary,
        }
    return {"slug": slug, "items": by_id}


class NewsClient:
    """Rate-limited feed fetcher. One instance per refresh run."""

    def __init__(self, ua: str = NEWS_UA):
        self.ua = ua
        self._last = 0.0

    def _get(self, url: str) -> bytes:
        wait = MIN_INTERVAL - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(url, headers={
            "User-Agent": self.ua,
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()
        finally:
            self._last = time.monotonic()

    def fetch_google_news(self, query: str, when_days: int = 60) -> list[NewsItem]:
        return parse_rss(self._get(google_news_url(query, when_days)), feed="google-news")

    def fetch_pr_feed(self, url: str) -> list[NewsItem]:
        return parse_rss(self._get(url), feed="pr")
