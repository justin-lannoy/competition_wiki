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
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import (  # noqa: E402
    PAGES, SEC_FILINGS_ROOT, WIKI_ROOT, CompetitorFiler, parse_competitors,
    write_page,
)
import sec_edgar as edgar  # noqa: E402


SUMMARY_SYSTEM = (
    "You are an equity analyst summarizing an SEC filing for Snap Finance, a "
    "point-of-sale financing / lease-to-own company that tracks competitors. "
    "Be concise, factual, and specific with numbers and dates."
)


def summarize_filing(client, form: str, filing_date: str, text: str,
                     model: str = "claude-sonnet-4-6") -> str:
    """Summarize one filing's text via the Anthropic API. Returns markdown."""
    if not text.strip():
        return ""  # missing/empty document — skip the billable call
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


def _rows_newest_first(sidecar: dict) -> list[dict]:
    rows = list(sidecar.get("filings", {}).values())
    return sorted(rows, key=lambda r: r.get("filing_date", ""), reverse=True)


def _clean_summary(text: str) -> str:
    """Drop level-4 summary sections whose only content is 'None noted',
    so tracker pages aren't padded with boilerplate."""
    sections: list[tuple[str | None, list[str]]] = []
    head, body = None, []
    for ln in (text or "").splitlines():
        if ln.startswith("#### "):
            sections.append((head, body)); head, body = ln, []
        else:
            body.append(ln)
    sections.append((head, body))
    def _is_none(b: str) -> bool:
        s = re.sub(r"^[-*]\s*", "", b).strip().lower()
        return s.startswith("none noted") or s.rstrip(".") in ("none", "none noted")

    keep: list[str] = []
    for head, body in sections:
        content = [b for b in body if b.strip()]
        only_none = bool(content) and all(_is_none(b) for b in content)
        if head is None:
            keep.extend(body)
        elif only_none or not content:
            continue
        else:
            keep.append(head); keep.extend(body)
    return "\n".join(keep).strip()


def _fmt_usd(v: float) -> str:
    a = abs(v)
    if a >= 1e9:
        return f"${v / 1e9:.2f}B"
    if a >= 1e6:
        return f"${v / 1e6:.1f}M"
    if a >= 1e3:
        return f"${v / 1e3:.0f}K"
    return f"${v:.0f}"


def _svg_line_chart(series: list[dict], *, color: str = "#1B844A",
                    w: int = 520, h: int = 130) -> str:
    """Inline SVG line chart for a quarterly series (no chart-lib dependency)."""
    if len(series) < 2:
        return ""
    vals = [p["val"] for p in series]
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    pad_x, pad_t, pad_b = 10, 14, 26
    n = len(series)
    X = lambda i: pad_x + i * (w - 2 * pad_x) / (n - 1)
    Y = lambda v: pad_t + (1 - (v - lo) / rng) * (h - pad_t - pad_b)
    poly = " ".join(f"{X(i):.1f},{Y(p['val']):.1f}" for i, p in enumerate(series))
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img">']
    if lo < 0 < hi:   # zero baseline (net income can go negative)
        out.append(f'<line x1="{pad_x}" y1="{Y(0):.1f}" x2="{w - pad_x}" y2="{Y(0):.1f}" '
                   'stroke="#CCCCCC" stroke-width="1"/>')
    out.append(f'<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="2"/>')
    for i in (0, n - 1):
        out.append(f'<circle cx="{X(i):.1f}" cy="{Y(series[i]["val"]):.1f}" r="3" fill="{color}"/>')
    out.append(f'<text x="{pad_x}" y="{h - 8}" font-size="10" fill="#696969">{series[0]["label"]}</text>')
    out.append(f'<text x="{w - pad_x}" y="{h - 8}" font-size="10" fill="#696969" '
               f'text-anchor="end">{series[-1]["label"]}</text>')
    out.append(f'<text x="{X(n - 1):.1f}" y="{max(Y(series[-1]["val"]) - 6, 10):.1f}" font-size="10" '
               f'fill="{color}" text-anchor="end">{_fmt_usd(series[-1]["val"])}</text>')
    out.append('</svg>')
    return "".join(out)


def _cell(value: str) -> str:
    """Escape a value for safe inclusion in a markdown table cell.

    Sidecar fields (form, dates) are committed JSON and could be hand-edited;
    a stray `|` would otherwise shift every following column.
    """
    return str(value).replace("|", "\\|")


def render_filer_page(filer: CompetitorFiler, sidecar: dict,
                      today: dt.date) -> tuple[dict, str]:
    """Render a per-filer SEC tracker page (frontmatter, body)."""
    rows = _rows_newest_first(sidecar)
    cik = sidecar.get("cik", "")
    # Pre-clean summaries; only filings whose summary survives cleaning get a
    # <details> block and a table anchor link (avoids empty/dead expanders).
    cleaned = {r["accession"]: _clean_summary(r.get("summary", "")) for r in rows}
    has_summary = {a for a, b in cleaned.items() if b.strip()}
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
        anchor = r["accession"].replace("-", "")
        form_cell = (f"[{_cell(r['form'])}](#f-{anchor})"
                     if r["accession"] in has_summary else _cell(r["form"]))
        parts.append(
            f"| {form_cell} | {_cell(r['filing_date'])} | "
            f"{_cell(period)} | {doc} | {local} |"
        )
    parts.append("")

    fin = sidecar.get("financials") or {}
    rev, ni = fin.get("revenue") or [], fin.get("net_income") or []
    if len(rev) >= 2 or len(ni) >= 2:
        parts += ["## Financial trends", "",
                  "_Quarterly, from SEC XBRL company facts._", ""]
        if len(rev) >= 2:
            parts += [f"**Revenue** — latest {rev[-1]['label']}: {_fmt_usd(rev[-1]['val'])}",
                      "", _svg_line_chart(rev, color="#1B844A"), ""]
        if len(ni) >= 2:
            parts += [f"**Net income** — latest {ni[-1]['label']}: {_fmt_usd(ni[-1]['val'])}",
                      "", _svg_line_chart(ni, color="#3D5CCF"), ""]

    summarized = [r for r in rows if r["accession"] in has_summary]
    if summarized:
        parts += ["## Filing summaries", "",
                  "_Click a filing to expand its summary._", ""]
        for r in summarized:
            anchor = r["accession"].replace("-", "")
            parts += [
                f'<details id="f-{anchor}">',
                f'<summary><strong>{r["form"]}</strong> — {r["filing_date"]}</summary>',
                "", cleaned[r["accession"]], "", "</details>", "",
            ]
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
            f"| [[{filer.filer_slug}]] | {_cell(filer.ticker)} | [[{filer.slug}]] | "
            f"{len(rows)} | {_cell(latest)} |"
        )
    parts.append("")
    return fm, "\n".join(parts)


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

    # XBRL financial time-series (for the tracker page's trend charts).
    facts = edgar_client.companyfacts(cik)
    fin = {
        "revenue": edgar.extract_quarterly_series(facts, edgar.REVENUE_CONCEPTS),
        "net_income": edgar.extract_quarterly_series(facts, edgar.NETINCOME_CONCEPTS),
    }
    if fin["revenue"] or fin["net_income"]:
        sidecar["financials"] = fin

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
