#!/usr/bin/env python3
"""Pull recent news + PR coverage for each competitor in competitors.md,
store items in per-competitor sidecars under news/, AI-summarize each article,
render news tracker pages under pages/news/, and rebuild the wiki.

Coverage comes from Google News RSS (no API key). Official press releases are
pulled from any `PR feed` URL listed for a competitor in competitors.md.

Usage:
    python scripts/refresh_news.py --use-anthropic-api   # pull + summarize
    python scripts/refresh_news.py --existing-only        # re-render offline
    python scripts/refresh_news.py --use-anthropic-api --dry-run
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import (  # noqa: E402
    PAGES, WIKI_ROOT, parse_competitor_registry, write_page,
)
import news_feeds as nf  # noqa: E402

NEWS_ROOT = WIKI_ROOT / "news"   # per-competitor _news.json sidecars

SUMMARY_SYSTEM = (
    "You are a competitive-intelligence analyst at Snap Finance, a point-of-sale "
    "financing / lease-to-own company that tracks competitors. Be concise and "
    "factual; never invent details beyond the headline and snippet provided."
)


def summarize_item(client, competitor: str, item: dict,
                   model: str = "claude-sonnet-4-6") -> str:
    """One Claude call per article: a 1-2 sentence read-through + a tag line."""
    snippet = (item.get("snippet") or "").strip()
    prompt = (
        f"Competitor: {competitor}\n"
        f"Headline: \"{item.get('title','')}\"\n"
        f"Source: {item.get('source','')} · {item.get('published','')}\n"
        f"Snippet: {snippet or '(none provided)'}\n\n"
        "In 1-2 sentences, summarize what happened and the read-through for Snap "
        "Finance. If the headline/snippet is too thin to tell, say so plainly. "
        "Then on a NEW line output exactly:\n"
        "Significance: <low|medium|high> · Category: "
        "<earnings|partnership|product|leadership|legal|funding|other>"
    )
    resp = client.messages.create(
        model=model, max_tokens=300, system=SUMMARY_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return "\n\n".join(
        b.text for b in resp.content if getattr(b, "type", "") == "text"
    ).strip()


def _cell(value: str) -> str:
    """Escape a value for a markdown table cell (a stray `|` shifts columns)."""
    return str(value).replace("|", "\\|").replace("\n", " ")


def _items_newest_first(sidecar: dict) -> list[dict]:
    rows = list(sidecar.get("items", {}).values())
    return sorted(rows, key=lambda r: r.get("published", ""), reverse=True)


def render_news_page(row: dict, sidecar: dict, today: dt.date) -> tuple[dict, str]:
    """Render a per-competitor news tracker page (frontmatter, body)."""
    slug = row["slug"]
    title = row.get("title") or slug
    items = _items_newest_first(sidecar)
    fm = {
        "title": f"{title} — Recent Coverage",
        "type": "news",
        "competitor": f"[[{slug}]]",
        "count": len(items),
        "created": today.isoformat(),
        "updated": today.isoformat(),
    }
    parts = [
        f"# {title} — Recent Coverage",
        "",
        f"_Updated: {today:%B %-d, %Y}_  ·  News & PR for [[{slug}]]",
        "",
    ]
    if not items:
        parts += ["_No coverage found in the current window._", ""]
        return fm, "\n".join(parts)

    parts += [
        "## Coverage",
        "",
        "| Date | Signal | Source | Headline |",
        "| --- | --- | --- | --- |",
    ]
    for r in items:
        date = r.get("published") or "—"
        src = r.get("source") or "—"
        tag = " · PR" if r.get("feed") == "pr" else ""
        sig = r.get("significance") or "—"
        headline = f"[{_cell(r.get('title',''))}]({r.get('url','')})"
        parts.append(f"| {_cell(date)} | {sig} | {_cell(src)}{tag} | {headline} |")
    parts.append("")

    # Coverage notes only for material (high/medium) items — low-signal stock
    # chatter stays in the table above but doesn't clutter the read-through.
    summarized = [r for r in items
                  if r.get("summary") and r.get("significance") in ("high", "medium")]
    if summarized:
        parts += ["## Coverage notes", ""]
        for r in summarized:
            head = f"### {r.get('published') or ''} — {r.get('source') or ''}".rstrip(" —")
            parts += [head, "", f"**{r.get('title','')}**", "", r["summary"], ""]
    return fm, "\n".join(parts)


def render_news_index(rows_sidecars: list[tuple[dict, dict]],
                      today: dt.date) -> tuple[dict, str]:
    """Render the news tracker index roll-up page."""
    total = sum(len(s.get("items", {})) for _, s in rows_sidecars)
    fm = {
        "title": "Competitor News — Tracker Index",
        "type": "news",
        "count": total,
        "created": today.isoformat(),
        "updated": today.isoformat(),
    }
    parts = [
        "# Competitor News — Tracker Index",
        "",
        f"_Updated: {today:%B %-d, %Y}_  ·  **{total}** items tracked across "
        f"**{len(rows_sidecars)}** competitors.",
        "",
        "| Competitor | Items | Latest |",
        "| --- | --- | --- |",
    ]
    for row, sidecar in sorted(rows_sidecars, key=lambda x: (x[0].get("title") or "").lower()):
        items = _items_newest_first(sidecar)
        latest = items[0]["published"] if items and items[0].get("published") else "—"
        parts.append(
            f"| [[{row['slug']}]] | {len(items)} | {_cell(latest)} |"
        )
    parts.append("")
    return fm, "\n".join(parts)


def _load_env() -> None:
    env_file = WIKI_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def _process_competitor(row: dict, news_client: "nf.NewsClient", anthropic_client,
                        today: dt.date, *, use_api: bool, dry_run: bool,
                        days: int, when_days: int, pr_days: int,
                        max_items: int) -> dict:
    """Fetch + filter + (optionally) summarize coverage for one competitor.

    Google News (high-volume, noisy) is kept to a tight `days` window; the
    official PR feed (sparse, always on-topic) gets a wider `pr_days` window so
    a low-frequency newsroom still surfaces several releases."""
    slug = row["slug"]
    title = row.get("title") or slug
    sidecar_path = NEWS_ROOT / slug / "_news.json"
    sidecar = nf.load_sidecar(sidecar_path)
    prior = {iid: r.get("summary", "") for iid, r in sidecar.get("items", {}).items()}

    # A registry `Search query` cell overrides the auto-built query (useful for
    # short/ambiguous names like Zip or HFD); otherwise derive from name+parent.
    query = (row.get("query") or "").strip() or nf.news_query(title, row.get("parent", ""))
    google: list[nf.NewsItem] = []
    try:
        google = nf.filter_recent(news_client.fetch_google_news(query, when_days),
                                  today, days=days)
    except Exception as e:  # one bad fetch must not abort the run
        print(f"\n    ! google-news fetch failed for {slug}: {e}", end="")
    pr: list[nf.NewsItem] = []
    pr_feed = (row.get("pr_feed") or "").strip()
    if pr_feed:
        try:
            pr = nf.filter_recent(news_client.fetch_pr_feed(pr_feed), today, days=pr_days)
        except Exception as e:
            print(f"\n    ! PR feed failed for {slug}: {e}", end="")

    # Denylist + cap the high-volume Google News stream; KEEP ALL official PR
    # items (sparse, authoritative — never crowd them out behind the cap).
    google = [it for it in nf.sort_newest_first(nf.dedupe(google)) if not nf.is_noise(it)]
    if len(google) > max_items:
        print(f"\n    · {slug}: capping news {len(google)} -> {max_items}", end="")
        google = google[:max_items]
    items = nf.sort_newest_first(nf.dedupe(google + pr))
    print(f"  · {title}: {len(items)} items ({len(pr)} PR)", end=" ")

    sidecar = nf.merge_sidecar(sidecar, slug, items)
    # Prune any previously-stored deny-listed noise so re-runs clean history.
    sidecar["items"] = {
        iid: r for iid, r in sidecar.get("items", {}).items()
        if not nf.is_noise(nf.NewsItem(
            title=r.get("title", ""), url=r.get("url", ""), source=r.get("source", ""),
            published=r.get("published", ""), feed=r.get("feed", "")))
    }
    # (Re)derive the structured significance tag from any existing summaries —
    # always re-parse so a fixed parser corrects prior values for free.
    for r in sidecar["items"].values():
        if r.get("summary"):
            r["significance"] = nf.parse_significance(r["summary"])

    if use_api and anthropic_client and not dry_run:
        new_count = 0
        for it in items:
            iid = nf.item_id(it)
            if prior.get(iid):
                continue  # already summarized
            try:
                summary = summarize_item(anthropic_client, title,
                                         sidecar["items"][iid])
                sidecar["items"][iid]["summary"] = summary
                sidecar["items"][iid]["significance"] = nf.parse_significance(summary)
                new_count += 1
            except Exception as e:
                print(f"\n    ! summary failed for {iid}: {e}", end="")
        print(f"({new_count} new summaries)", end=" ")

    if not dry_run:
        sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        sidecar_path.write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
    print("✓")
    return sidecar


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--use-anthropic-api", action="store_true",
                    help="Fetch coverage and generate/refresh AI summaries")
    ap.add_argument("--existing-only", action="store_true",
                    help="Re-render tracker pages from local sidecars (offline)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Report what would happen without writing")
    ap.add_argument("--days", type=int, default=60,
                    help="Keep items filed within this many days (default 60)")
    ap.add_argument("--when-days", type=int, default=60,
                    help="Google News search recency window (default 60)")
    ap.add_argument("--pr-days", type=int, default=365,
                    help="Retain official PR-feed items this many days (default 365)")
    ap.add_argument("--max-items", type=int, default=25,
                    help="Cap items kept per competitor (default 25)")
    args = ap.parse_args(argv)

    if not args.use_anthropic_api and not args.existing_only:
        ap.error("provide --use-anthropic-api or --existing-only")

    today = dt.date.today()
    rows = parse_competitor_registry()
    print(f"News refresh for {len(rows)} competitors…")

    anthropic_client = None
    if args.use_anthropic_api:
        _load_env()
        try:
            from anthropic import Anthropic
        except ImportError:
            print("ERROR: pip install anthropic", file=sys.stderr)
            return 2
        anthropic_client = Anthropic()

    rows_sidecars: list[tuple[dict, dict]] = []

    if args.existing_only:
        for row in rows:
            sidecar = nf.load_sidecar(NEWS_ROOT / row["slug"] / "_news.json")
            rows_sidecars.append((row, sidecar))
    else:
        news_client = nf.NewsClient()
        for row in rows:
            try:
                sidecar = _process_competitor(
                    row, news_client, anthropic_client, today,
                    use_api=args.use_anthropic_api, dry_run=args.dry_run,
                    days=args.days, when_days=args.when_days,
                    pr_days=args.pr_days, max_items=args.max_items)
            except Exception as e:  # one bad competitor must not abort the run
                print(f"  ! {row['slug']}: {e} — skipping")
                sidecar = nf.load_sidecar(NEWS_ROOT / row["slug"] / "_news.json")
            rows_sidecars.append((row, sidecar))

    if args.dry_run:
        print("· dry-run: no pages written, no wiki rebuild")
        return 0

    out_dir = PAGES / "news"
    for row, sidecar in rows_sidecars:
        fm, body = render_news_page(row, sidecar, today)
        write_page(out_dir / f"{row['slug']}.md", fm, body, overwrite=True)
    fm, body = render_news_index(rows_sidecars, today)
    write_page(out_dir / "index.md", fm, body, overwrite=True)
    print(f"  · wrote {len(rows_sidecars)} news pages + index")

    print("  · rebuilding wiki…")
    subprocess.run(["python3", "build_wiki.py", "--no-embed-key"],
                   cwd=WIKI_ROOT, check=True)
    print("  ✓ news refresh complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
