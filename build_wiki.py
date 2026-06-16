#!/usr/bin/env python3
"""Compile every markdown page in `pages/` into a single self-contained
`pages/wiki.html` SPA, ready to drop on RStudio Connect.

Adapted from `snap-insights-wiki-master/build_wiki.py`. Differences:
- BASE resolves from this file's location (no Windows hard-coding).
- Managed-accounts page types: edition, event, partner, competitor, sae,
  segment, source.
- KORT slide-mapping logic stripped — managed-accounts pages don't have
  attached deck images.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
os.chdir(BASE)


def parse_frontmatter(text: str) -> dict:
    """Minimal YAML frontmatter parser — same dialect as the insights wiki."""
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
        if value.startswith("[") and value.endswith("]"):
            fm[key] = [
                x.strip().strip("\"'")
                for x in value[1:-1].split(",")
                if x.strip()
            ]
        else:
            # strip surrounding quotes if present
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            fm[key] = value
    return fm


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
    ("pages/news", "news"),
]


def collect_pages() -> list[dict]:
    pages: list[dict] = []
    for rel_dir, default_type in PAGE_DIRS:
        dpath = BASE / rel_dir
        if not dpath.exists():
            continue
        for fname in sorted(os.listdir(dpath)):
            if not fname.endswith(".md"):
                continue
            slug = fname[:-3]
            raw = (dpath / fname).read_text(encoding="utf-8")
            fm = parse_frontmatter(raw)
            def _unwiki(val):
                if isinstance(val, list):
                    val = ", ".join(val)
                return re.sub(r"\[+|\]+", "", val) if val else ""

            seg = _unwiki(fm.get("segment", ""))
            sae = _unwiki(fm.get("sae", ""))
            partner = _unwiki(fm.get("partner", ""))
            competitor = _unwiki(fm.get("competitor", ""))
            pages.append({
                "slug": slug,
                "type": fm.get("type", default_type),
                "title": fm.get("title", slug),
                "significance": fm.get("significance", ""),
                "significance_reason": fm.get("significance_reason", ""),
                "category": fm.get("category", ""),
                "tier": fm.get("tier", ""),
                "segment": seg,
                "sae": sae,
                "partner": partner,
                "competitor": competitor,
                "date": fm.get("date", ""),
                "parent": fm.get("parent", "") or fm.get("parent_brand", ""),
                "ticker": fm.get("ticker", ""),
                "publisher": fm.get("publisher", ""),
                "url": fm.get("url", ""),
                "owner_name": fm.get("owner_name", ""),
                "owner_slug": fm.get("owner_slug", ""),
                "count": fm.get("count", ""),
                "tags": fm.get("tags", []),
                "sources": fm.get("sources", []),
                "content": raw,
            })
    return pages


COMPETITOR_REGISTRY = BASE / "competitors.md"

# Canonical row keys -> accepted header substrings (mirrors scripts/_lib.py;
# build_wiki stays standalone and parses the registry itself, just as it has
# its own parse_frontmatter).
_REG_COLS = {
    "slug": ("slug",), "title": ("competitor", "name", "title"),
    "parent": ("parent", "issuer"), "ticker": ("ticker", "symbol"),
    "category": ("category",), "notes": ("note",),
}


def parse_registry(path: Path) -> list[dict]:
    """Parse the competitor registry markdown table into canonical row dicts."""
    if not path.exists():
        return []
    header = None
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("|"):
            continue
        s = line.strip().strip("|")
        cells = [c.strip() for c in s.split("|")]
        if all(c and set(c) <= set("-: ") for c in cells):  # separator row
            continue
        if header is None:
            lowered = [c.lower() for c in cells]
            header = {}
            for canon, keys in _REG_COLS.items():
                for i, h in enumerate(lowered):
                    if any(k in h for k in keys):
                        header[canon] = i
                        break
            continue
        row = {c: (cells[i].strip() if i < len(cells) else "")
               for c, i in header.items()}
        if row.get("slug"):
            rows.append(row)
    return rows


def _blank_competitor(slug: str) -> dict:
    """An empty competitor page dict with every field collect_pages emits."""
    return {
        "slug": slug, "type": "competitor", "title": slug, "significance": "",
        "significance_reason": "", "category": "", "tier": "", "segment": "",
        "sae": "", "partner": "", "competitor": "", "date": "", "parent": "",
        "ticker": "", "publisher": "", "url": "", "owner_name": "",
        "owner_slug": "", "count": "", "tags": [], "sources": [], "content": "",
    }


def _recent_news(slug: str, limit: int = 3) -> list[dict]:
    """Top-N most recent news items for a competitor, from its sidecar.

    Embedded into the competitor page data so Competitor Watch can show a
    'Latest coverage' line for competitors that have no curated events."""
    sidecar = BASE / "news" / slug / "_news.json"
    if not sidecar.exists():
        return []
    try:
        items = json.loads(sidecar.read_text(encoding="utf-8")).get("items", {})
    except (json.JSONDecodeError, OSError):
        return []
    rows = sorted(items.values(), key=lambda r: r.get("published", ""), reverse=True)
    return [
        {"date": r.get("published", ""), "source": r.get("source", ""),
         "title": r.get("title", ""), "url": r.get("url", "")}
        for r in rows[:limit]
    ]


def _synth_competitor_body(p: dict) -> str:
    """Minimal editorial body for a registry competitor with no page yet."""
    title = p.get("title") or p.get("slug")
    cat = (p.get("category") or "").strip()
    parent = (p.get("parent") or "").strip()
    cat_clause = f" in the {cat} category" if cat else ""
    parent_clause = ""
    if parent and parent.lower() not in (title.lower(), "") and "private" not in parent.lower():
        parent_clause = f" Its SEC filer / parent is {parent}."
    return (
        f"# {title}\n\n## Overview\n\n"
        f"{title} is tracked as a Snap Finance competitor{cat_clause}.{parent_clause}\n\n"
        "_No editorial notes yet — recent moves and SEC filings populate on the next refresh._\n"
    )


def merge_competitor_registry(pages: list[dict]) -> list[dict]:
    """Make competitors.md authoritative: emit one competitor page per registry
    row, overriding roster fields and reusing any matching editorial page body."""
    rows = parse_registry(COMPETITOR_REGISTRY)
    if not rows:
        return pages
    existing = {p["slug"]: p for p in pages if p.get("type") == "competitor"}
    merged: list[dict] = []
    for r in rows:
        slug = r["slug"]
        p = dict(existing.get(slug) or _blank_competitor(slug))
        p["type"], p["slug"] = "competitor", slug
        for field in ("title", "parent", "ticker", "category"):
            if r.get(field):
                p[field] = r[field]
        if not (p.get("content") or "").strip():
            p["content"] = _synth_competitor_body(p)
        p["recent_news"] = _recent_news(slug)
        merged.append(p)
    others = [p for p in pages if p.get("type") != "competitor"]
    return others + merged


def load_env_vars() -> tuple[str, str]:
    """Read ANTHROPIC_API_KEY and CLAUDE_PROXY_URL from .env."""
    api_key = ""
    proxy_url = ""
    env_path = BASE / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip()
                if k == "ANTHROPIC_API_KEY":
                    api_key = v
                elif k == "CLAUDE_PROXY_URL":
                    proxy_url = v
    return api_key, proxy_url


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # Default: do NOT embed the API key into the built HTML — the proxy at
    # CLAUDE_PROXY_URL handles auth at request time, and the committed
    # `pages/wiki.html` must never carry a live key. Pass `--embed-key` (or
    # set WIKI_BUILD_EMBED_KEY=1) to opt in for a one-off local build that
    # talks to Anthropic directly. `--no-embed-key` is still accepted as a
    # no-op so the existing automation in refresh_briefing.py /
    # refresh_industry_reports.py keeps working unchanged.
    embed_key = (
        "--embed-key" in argv
        or os.environ.get("WIKI_BUILD_EMBED_KEY", "").strip() in {"1", "true", "yes"}
    )
    for flag in ("--embed-key", "--no-embed-key"):
        while flag in argv:
            argv.remove(flag)
    no_embed_key = not embed_key

    pages = collect_pages()
    pages = merge_competitor_registry(pages)
    wiki_json = json.dumps(pages, ensure_ascii=True).replace("</", r"<\/")

    print(f"Pages: {len(pages)}, JSON size: {len(wiki_json):,} chars")

    app_js_path = BASE / "wiki_app.js"
    if not app_js_path.exists():
        print("ERROR: wiki_app.js not found — run after porting it.", file=sys.stderr)
        return 2
    app_js = app_js_path.read_text(encoding="utf-8")

    css_path = BASE / "wiki_styles.css"
    if not css_path.exists():
        print("ERROR: wiki_styles.css not found — run after porting it.", file=sys.stderr)
        return 2
    css = css_path.read_text(encoding="utf-8")

    enhance_path = BASE / "wiki_enhance.js"
    enhance_js = enhance_path.read_text(encoding="utf-8") if enhance_path.exists() else ""

    api_key, proxy_url = load_env_vars()
    if no_embed_key:
        if api_key:
            print(f"API key:   SUPPRESSED — loaded from .env ({api_key[:12]}…) but not embedded (default; pass --embed-key for local builds)")
        else:
            print("API key:   not set and suppressed — build relies on the proxy")
        api_key = ""
    elif api_key:
        print(f"API key:   embedded ({api_key[:12]}…) — DO NOT COMMIT this build")
    else:
        print("API key:   not set — users will be prompted")
    if proxy_url:
        print(f"Proxy URL: {proxy_url}")
    else:
        print("Proxy URL: not set — direct Anthropic calls (will fail under org CORS)")

    html = HTML_TEMPLATE.format(css=css, wiki_json=wiki_json, app_js=app_js,
                                enhance_js=enhance_js,
                                proxy_url=proxy_url, api_key=api_key)
    out = BASE / "pages" / "wiki.html"
    out.write_text(html, encoding="utf-8")
    print(f"Final HTML: {len(html):,} chars")
    print(f"Written: {out.relative_to(BASE)}")

    # Sanity-check: round-trip the JSON we embedded.
    start = html.find('<script type="application/json" id="wiki-data">') + len(
        '<script type="application/json" id="wiki-data">'
    )
    end = html.find("</script>", start)
    try:
        data = json.loads(html[start:end])
        print(f"JSON valid: {len(data)} pages parsed OK")
    except Exception as e:
        print(f"JSON ERROR: {e}", file=sys.stderr)
        return 3
    return 0


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Competitor Intelligence — Snap Finance</title>
<meta name="wiki-proxy-url" content="{proxy_url}">
<meta name="wiki-api-key" content="{api_key}">
<script src="https://unpkg.com/react@18.3.1/umd/react.development.js" integrity="sha384-hD6/rw4ppMLGNu3tX5cjIb+uRZ7UkRJ6BPkLpg4hAu/6onKUg4lLsHAs9EBPT82L" crossorigin="anonymous"></script>
<script src="https://unpkg.com/react-dom@18.3.1/umd/react-dom.development.js" integrity="sha384-u6aeetuaXnQ38mYT8rp6sbXaQe3NL9t+IBXmnYxwkUI2Hw4bsp2Wvmx4yRQF1uAm" crossorigin="anonymous"></script>
<script src="https://unpkg.com/@babel/standalone@7.29.0/babel.min.js" integrity="sha384-m08KidiNqLdpJqLq95G/LEi8Qvjl/xUYll3QILypMoQ65QorJ9Lvtp2RXYGBFj1y" crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/npm/marked@12.0.0/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/dompurify@3.0.9/dist/purify.min.js"></script>
<style>
{css}
</style>
</head>
<body>
<div id="root">
  <div style="display:flex;height:100vh;align-items:center;justify-content:center;flex-direction:column;gap:12px;font-family:Arial,'Helvetica Neue',Helvetica,sans-serif;color:#696969;background:#fff;">
    <div style="font-size:14px;font-weight:700;color:#3D5CCF;letter-spacing:.14em;text-transform:uppercase;">Loading Competitor Intelligence…</div>
    <noscript>
      <div style="margin-top:14px;padding:12px 18px;border:1px solid #A32D2D;background:#FCEBEB;border-radius:4px;color:#A32D2D;max-width:520px;text-align:center;font-size:13px;">
        JavaScript is required to view this wiki. Please enable JavaScript or contact your administrator.
      </div>
    </noscript>
  </div>
</div>
<script type="application/json" id="wiki-data">{wiki_json}</script>
<script type="text/babel">
{app_js}
</script>
<script>
{enhance_js}
</script>
</body>
</html>
"""


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
