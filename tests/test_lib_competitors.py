import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from _lib import (  # noqa: E402
    parse_competitors, parse_competitor_registry, CompetitorFiler,
)

HEADER = (
    "| Slug | Competitor | Parent (SEC issuer) | Ticker | Category | Notes |\n"
    "| --- | --- | --- | --- | --- | --- |\n"
)


def _registry(tmp_path: Path, rows: str) -> Path:
    p = tmp_path / "competitors.md"
    p.write_text("# Competitor Registry\n\n" + HEADER + rows, encoding="utf-8")
    return p


def test_parse_competitors_extracts_public_filers(tmp_path):
    reg = _registry(tmp_path,
        "| acima | Acima | Upbound Group | UPBD | lto | |\n"
        "| koalafi | Koalafi | Koalafi (private) | private | pos-financing | |\n"
        "| klarna | Klarna Group | Klarna Group | KLAR | bnpl | |\n")

    filers = parse_competitors(reg)

    assert all(isinstance(f, CompetitorFiler) for f in filers)
    slugs = {f.slug for f in filers}
    assert slugs == {"acima", "klarna"}            # private skipped
    acima = next(f for f in filers if f.slug == "acima")
    assert acima.title == "Acima"
    assert acima.parent == "Upbound Group"
    assert acima.ticker == "UPBD"
    assert acima.filer_slug == "upbound-group"      # slugify(parent)
    klarna = next(f for f in filers if f.slug == "klarna")
    assert klarna.title == "Klarna Group"
    assert klarna.filer_slug == "klarna-group"      # multi-word slugify(parent)


def test_parse_competitors_skips_missing_parent(tmp_path):
    reg = _registry(tmp_path, "| x | X |  | XYZ | lto | |\n")
    assert parse_competitors(reg) == []


def test_parse_competitor_registry_reads_all_rows(tmp_path):
    reg = _registry(tmp_path,
        "| acima | Acima | Upbound Group | UPBD | lto | brand |\n"
        "| koalafi | Koalafi | Koalafi (private) | private | pos-financing | |\n")
    rows = parse_competitor_registry(reg)
    assert [r["slug"] for r in rows] == ["acima", "koalafi"]
    assert rows[0]["category"] == "lto"
    assert rows[0]["notes"] == "brand"
    assert rows[1]["ticker"] == "private"


def test_parse_competitor_registry_tolerates_reordered_columns(tmp_path):
    p = tmp_path / "competitors.md"
    p.write_text(
        "| Ticker | Slug | Category | Parent | Competitor |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| SEZL | sezzle | bnpl | Sezzle Inc. | Sezzle |\n",
        encoding="utf-8")
    filers = parse_competitors(p)
    assert len(filers) == 1
    assert filers[0].slug == "sezzle"
    assert filers[0].ticker == "SEZL"
    assert filers[0].filer_slug == "sezzle-inc"
