"""Shared helpers for the wiki seed and refresh scripts.

Single source of truth for slug conventions, the Partners_By_SAE workbook
parser, and atomic markdown writes. Anything that touches the on-disk wiki
structure should go through this module so the entry-point scripts stay
consistent.
"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

WIKI_ROOT = Path(__file__).resolve().parent.parent
PAGES = WIKI_ROOT / "pages"
SEC_FILINGS_ROOT = WIKI_ROOT / "sec-filings"
COMPETITOR_REGISTRY = WIKI_ROOT / "competitors.md"

TIER_SUFFIXES = [
    "LM Northeast", "LM-Northeast",
    "LM Southeast", "LM-Southeast",
    "LM West", "LM-West",
    "LM Corporate", "LM-Corporate",
    "Enterprise",
    "LM",
]

TIER_NORMALIZED = {
    "LM Northeast": "lm-northeast", "LM-Northeast": "lm-northeast",
    "LM Southeast": "lm-southeast", "LM-Southeast": "lm-southeast",
    "LM West": "lm-west", "LM-West": "lm-west",
    "LM Corporate": "lm-corporate", "LM-Corporate": "lm-corporate",
    "Enterprise": "enterprise",
    "Tech Partner": "tech-partner",
    "LM": "lm",
}

# Heuristic vertical/segment hints — used by seed_partners to fill `segment:`.
# Order matters: first match wins. Keep the right-hand slug stable (it becomes
# the segment page filename) once partner pages start citing it.
INDUSTRY_SLUG_MAP: dict[str, str] = {
    "Wheel & Tire": "wheel-tire",
    "Auto Service": "auto-service",
    "Collision": "collision",
    "Furniture": "furniture",
    "Mattresses": "mattresses",
    "Appliances": "appliances",
    "Elective Medical": "elective-medical",
    "Medical Devices": "medical-devices",
    "Car Audio": "car-audio",
    "Waterfall": "waterfall",
}

SEGMENT_HINTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(tire|tires|wheel)\b", re.I), "wheel-tire"),
    (re.compile(r"\b(meineke|midas|aamco|maaco|brake|lube|auto repair|auto care|automotive|auto group|transmission|sun auto|stress free|fast lap|point s|technet|pep boys|o'?reilly)\b", re.I), "auto-service"),
    (re.compile(r"\b(collision|body|paint)\b", re.I), "collision"),
    (re.compile(r"\b(mattress|sleep|slumber|bed|matts|snooze)\b", re.I), "mattresses"),
    (re.compile(r"\b(furniture|home ?store|gallery|knoxville|nfm|ashley|steinhafels|hometown|gardner|woodley|olum|jerusalem|brandsource|furniture first|price buster|regency|lacks)\b", re.I), "furniture"),
    (re.compile(r"\b(appliance|outlet|fred|orville|famous tate)\b", re.I), "appliances"),
    (re.compile(r"\b(laseraway|removery)\b", re.I), "elective-medical"),
    (re.compile(r"\b(good feet)\b", re.I), "medical-devices"),
    (re.compile(r"\b(tint world|mea|car audio)\b", re.I), "car-audio"),
]


# ---------------------------------------------------------------------------
# Slugging
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    """Lowercase, ASCII, hyphens-only slug.

    - drop apostrophes (`O'Reilly` -> `oreilly`, `Mancini's` -> `mancinis`)
    - `&` becomes `and`
    - whitespace and punctuation collapse to single hyphens
    - leading/trailing hyphens trimmed
    """
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.replace("&", " and ")
    text = re.sub(r"['’]", "", text)
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text)
    text = text.strip("-").lower()
    return re.sub(r"-+", "-", text)


def partner_slug(display_name: str) -> str:
    """Slug a partner display name, dropping common noise words like 'Group'."""
    cleaned = re.sub(r"\b(Group|LLC|Inc|Corp|Corporation|Co)\b\.?", "", display_name)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" -")
    return slugify(cleaned)


def guess_segment(display_name: str) -> str | None:
    for pattern, segment in SEGMENT_HINTS:
        if pattern.search(display_name):
            return segment
    return None


def parse_frontmatter(text: str) -> dict:
    """Minimal YAML frontmatter parser (same dialect as build_wiki.py).

    Note: values containing a colon are truncated at the first colon, and
    quoted values are unquoted but not further escaped. Current competitor
    frontmatter uses plain single-token values, so this is not a live concern.
    """
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


# ---------------------------------------------------------------------------
# Partner record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Partner:
    raw: str          # original line, post-strip ("Mavis Tire - Enterprise")
    display: str      # cleaned brand portion ("Mavis Tire")
    slug: str         # filename slug ("mavis-tire")
    sae_name: str     # "Jason Armetta"
    sae_slug: str     # "jason-armetta"
    tier: str | None  # "enterprise" | "lm" | "lm-west" | ...
    segment: str | None
    search_name: str = ""  # left of first " - " — the brand name to search for news


@dataclass(frozen=True)
class CompetitorFiler:
    """A publicly traded competitor and its SEC filer identity."""
    slug: str         # competitor page slug, e.g. "acima"
    title: str        # display title, e.g. "Acima"
    parent: str       # SEC issuer / parent, e.g. "Upbound Group"
    ticker: str       # e.g. "UPBD"
    filer_slug: str   # slugify(parent), e.g. "upbound-group"


# Maps registry table headers (lower-cased) to canonical row keys. Matching is
# by substring so the column can be renamed ("Parent (SEC issuer)" → "parent")
# without breaking the parser.
_REGISTRY_COLUMNS: dict[str, tuple[str, ...]] = {
    "slug": ("slug",),
    "title": ("competitor", "name", "title"),
    "parent": ("parent", "issuer"),
    "ticker": ("ticker", "symbol"),
    "category": ("category",),
    "tier": ("tier", "threat"),
    "product": ("product", "structure"),
    "query": ("search query", "query", "search"),
    "pr_feed": ("pr feed", "newsroom", "pr_feed"),
    "notes": ("note",),
}

VALID_CATEGORIES = {"lto", "bnpl", "pos-financing", "medical-financing"}
VALID_TIERS = {"direct-lto", "adjacent-bnpl", "prime-card", "medical"}


def _split_md_row(line: str) -> list[str]:
    """Split a markdown table row into trimmed cells, dropping the edge pipes."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _is_separator_row(cells: list[str]) -> bool:
    """True for the `| --- | --- |` divider under a markdown table header."""
    return all(c and set(c) <= set("-: ") for c in cells)


def parse_competitor_registry(path: Path | None = None) -> list[dict]:
    """Parse the competitor registry markdown table into row dicts.

    Returns one dict per data row with canonical keys (slug, title, parent,
    ticker, category, notes). The first pipe-row is the header; the column
    order is read from it, so columns can be reordered or renamed freely.
    Rows without a `slug` are skipped.
    """
    if path is None:
        path = COMPETITOR_REGISTRY
    text = path.read_text(encoding="utf-8")
    header_idx: dict[str, int] | None = None
    rows: list[dict] = []
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = _split_md_row(line)
        if _is_separator_row(cells):
            continue
        if header_idx is None:
            lowered = [c.lower() for c in cells]
            header_idx = {}
            for canon, keys in _REGISTRY_COLUMNS.items():
                for i, h in enumerate(lowered):
                    if any(k in h for k in keys):
                        header_idx[canon] = i
                        break
            continue
        row = {
            canon: (cells[i].strip() if i < len(cells) else "")
            for canon, i in header_idx.items()
        }
        if row.get("slug"):
            rows.append(row)
    _validate_registry(rows)
    return rows


def _validate_registry(rows: list[dict]) -> None:
    """Warn (non-fatal) on unknown category/tier values so typos surface."""
    import sys
    for r in rows:
        cat = (r.get("category") or "").strip().lower()
        tier = (r.get("tier") or "").strip().lower()
        if cat and cat not in VALID_CATEGORIES:
            print(f"  ! registry: {r['slug']} has unknown category '{cat}' "
                  f"(expected {sorted(VALID_CATEGORIES)})", file=sys.stderr)
        if tier and tier not in VALID_TIERS:
            print(f"  ! registry: {r['slug']} has unknown tier '{tier}' "
                  f"(expected {sorted(VALID_TIERS)})", file=sys.stderr)


def parse_competitors(registry_path: Path | None = None) -> list[CompetitorFiler]:
    """Enumerate publicly traded competitors from the competitor registry.

    Reads `competitors.md` (the single source of truth). Skips rows whose
    `ticker` is empty or `private`, and rows with no `parent` (the SEC issuer).
    The filer slug is derived from `parent` so two brands under one issuer
    resolve to the same filing tracker.
    """
    out: list[CompetitorFiler] = []
    for r in parse_competitor_registry(registry_path):
        ticker = (r.get("ticker") or "").strip()
        if not ticker or ticker.lower() == "private":
            continue
        parent = (r.get("parent") or "").strip()
        if not parent:
            continue
        out.append(CompetitorFiler(
            slug=r["slug"],
            title=(r.get("title") or r["slug"]).strip(),
            parent=parent,
            ticker=ticker,
            filer_slug=slugify(parent),
        ))
    return out


# ---------------------------------------------------------------------------
# Excel parser (canonical source)
# ---------------------------------------------------------------------------
# The Partners_By_SAE workbook is the single source of truth for the partner
# universe. It is resolved at call time (not import time) so the weekly refresh
# always reads whatever workbook is currently in pages/assets/ — dropping in a
# newer `Partners_By_SAE_<M.D.YY>.xlsx` is picked up on the next run with no
# code change.

PARTNERS_XLSX_DIR = WIKI_ROOT / "pages" / "assets"
PARTNERS_XLSX_GLOB = "Partners_By_SAE_*.xlsx"


def _xlsx_date_key(path: Path) -> tuple[int, dt.date]:
    """Sort key from the M.D.YY date embedded in the filename.

    `Partners_By_SAE_5.1.26.xlsx` -> (1, 2026-05-01). Files whose name doesn't
    carry a parseable date sort oldest, so a correctly-named newer workbook
    always wins. We key off the filename date rather than mtime because
    `git checkout` rewrites mtimes to clone time, which would scramble ordering
    in a fresh clone.
    """
    m = re.search(r"Partners_By_SAE_(\d{1,2})\.(\d{1,2})\.(\d{2,4})", path.name)
    if m:
        mo, day, yr = (int(g) for g in m.groups())
        if yr < 100:
            yr += 2000
        try:
            return (1, dt.date(yr, mo, day))
        except ValueError:
            pass
    return (0, dt.date.min)


def resolve_partners_xlsx(assets_dir: Path = PARTNERS_XLSX_DIR) -> Path:
    """Return the newest partner workbook in `assets_dir`.

    Raises FileNotFoundError if none exists. The partner list is required input
    for the pipeline, so callers hard-fail rather than run on a guessed roster.
    """
    candidates = sorted(assets_dir.glob(PARTNERS_XLSX_GLOB), key=_xlsx_date_key)
    if not candidates:
        raise FileNotFoundError(
            f"No partner workbook found matching "
            f"{assets_dir}/{PARTNERS_XLSX_GLOB}. The pipeline requires the "
            "Partners_By_SAE Excel as its source of truth."
        )
    return candidates[-1]


def _strip_tier_suffix(raw: str) -> tuple[str, str | None]:
    """Strip trailing tier classification from a partner name string."""
    s = raw.strip()
    for suffix in TIER_SUFFIXES:
        pattern = rf"\s*-?\s*{re.escape(suffix)}\s*$"
        m = re.search(pattern, s, re.I)
        if m:
            return s[: m.start()].rstrip(" -"), TIER_NORMALIZED[suffix]
    return s, None


def parse_partners_xlsx(xlsx_path: Path | None = None) -> list[Partner]:
    """Parse the Partners_By_SAE Excel file into Partner records.

    Columns: Partner, Sector, SAE, Industry. When `xlsx_path` is None the
    newest workbook in pages/assets/ is resolved at call time.
    """
    if xlsx_path is None:
        xlsx_path = resolve_partners_xlsx()
    try:
        import openpyxl
    except ImportError as e:
        raise RuntimeError("openpyxl required: pip install openpyxl") from e

    wb = openpyxl.load_workbook(xlsx_path)
    ws = wb.active
    partners: list[Partner] = []

    for row in ws.iter_rows(min_row=2, values_only=True):
        raw_name = str(row[0] or "").strip()
        sector = str(row[1] or "").strip()
        sae_name = str(row[2] or "").strip()
        industry = str(row[3] or "").strip()
        if not raw_name or not sae_name:
            continue

        display, tier = _strip_tier_suffix(raw_name)
        if not display:
            continue
        if not tier and sector:
            tier = TIER_NORMALIZED.get(sector)

        segment = INDUSTRY_SLUG_MAP.get(industry) or guess_segment(display)
        search = display.split(" - ")[0].strip()

        partners.append(
            Partner(
                raw=raw_name,
                display=display,
                slug=partner_slug(display),
                sae_name=sae_name,
                sae_slug=slugify(sae_name),
                tier=tier,
                segment=segment,
                search_name=search,
            )
        )

    wb.close()
    return partners


def waterfall_partner_slugs(xlsx_path: Path | None = None) -> set[str]:
    """Return the set of partner slugs whose Excel Industry column is 'Waterfall'.

    Waterfall partners are tech platforms (not retail merchants); the search
    pipeline routes them through a different system prompt that targets
    merchant-partnership announcements rather than store/earnings news.
    """
    return {p.slug for p in parse_partners_xlsx(xlsx_path) if p.segment == "waterfall"}


# ---------------------------------------------------------------------------
# Frontmatter writer
# ---------------------------------------------------------------------------

def yaml_value(v) -> str:
    """Format a single frontmatter value matching the existing pages' style."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    if s.startswith("[[") and s.endswith("]]"):
        return s
    if any(ch in s for ch in ":#&*?!|>'\""):
        return f'"{s}"'
    return s


def render_frontmatter(fields: dict) -> str:
    lines = ["---"]
    for k, v in fields.items():
        lines.append(f"{k}: {yaml_value(v)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def replace_section_body(text: str, heading: str, new_body: str, *, until: str) -> str:
    """Replace the body of a named H2 section in `text`, keeping the heading.

    The replaced range is everything between `## {heading}` and the *next*
    occurrence of `## {until}`. The new body is inserted with a leading
    blank line so it reads cleanly under the heading.

    `until` is required (no end-of-file fallback) because this function is
    used to surgically rewrite a *middle* section — the caller must name
    the known terminator section that follows. If the heading is missing,
    `text` is returned unchanged; if the terminator is missing, the
    section is treated as running to EOF.

    Companion to `preserve_section`: that one extracts a section so a
    full-rewrite generator can re-insert it; this one rewrites a section
    in place inside an otherwise hand-curated page.
    """
    start_pattern = re.compile(rf"^##\s+{re.escape(heading)}\s*\n", re.MULTILINE)
    start_match = start_pattern.search(text)
    if not start_match:
        return text
    end_pattern = re.compile(rf"^##\s+{re.escape(until)}\s*\n", re.MULTILINE)
    end_match = end_pattern.search(text, start_match.end())
    end_pos = end_match.start() if end_match else len(text)
    new_section = f"## {heading}\n\n{new_body.rstrip()}\n\n"
    return text[: start_match.start()] + new_section + text[end_pos:]


def preserve_section(path: Path, heading: str, *, until: str | None = None) -> str | None:
    """Read an existing markdown file and extract a named H2 section verbatim.

    Returns the section starting at `## {heading}` through end-of-file (or
    through the line before `## {until}` if `until` is given). Returns None
    if the file doesn't exist or the heading isn't present.

    The `until` parameter exists because AI-generated content sometimes
    emits H2 sub-headings (e.g. `## 1. Industry Overview`) inside what we
    consider a single logical section, so we can't use "next H2" as the
    boundary in general. Pass the name of the known terminator section
    (e.g. `until="Recent Headlines"` for an industry page's Research block)
    to scan past nested H2s safely. For sections that run to end-of-file
    (e.g. SAE `## Notes`), leave `until` as None.

    Used by the SAE and industry-page generators so weekly refreshes can
    rewrite dynamic content (stats, rosters, recent headlines) while
    preserving the hand-curated `## Notes` and AI-generated
    `## Research & Trends` sections in place.
    """
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    if until is not None:
        terminator = rf"(?=^##\s+{re.escape(until)}\s*\n|\Z)"
    else:
        terminator = r"\Z"
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*\n(.*?){terminator}",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(text)
    if not m:
        return None
    body = m.group(1).rstrip()
    return f"## {heading}\n{body}\n" if body else f"## {heading}\n"


def write_page(path: Path, frontmatter: dict, body: str, *, overwrite: bool = False) -> bool:
    """Write a markdown page atomically. Returns True if written, False if skipped."""
    if path.exists() and not overwrite:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    content = render_frontmatter(frontmatter) + "\n" + body.rstrip() + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)
    return True


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

def group_partners_by_sae(partners: Iterable[Partner]) -> dict[str, list[Partner]]:
    out: dict[str, list[Partner]] = {}
    for p in partners:
        out.setdefault(p.sae_name, []).append(p)
    for k in out:
        out[k].sort(key=lambda x: x.display.lower())
    return out
