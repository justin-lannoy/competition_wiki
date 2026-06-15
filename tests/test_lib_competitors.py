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
    assert acima.title == "Acima"
    assert acima.parent == "Upbound Group"
    assert acima.ticker == "UPBD"
    assert acima.filer_slug == "upbound-group"      # slugify(parent)
    klarna = next(f for f in filers if f.slug == "klarna")
    assert klarna.title == "Klarna Group"
    assert klarna.filer_slug == "klarna-group"      # multi-word slugify(parent)


def test_parse_competitors_skips_missing_parent(tmp_path):
    _write(tmp_path, "x.md",
           "---\ntitle: X\ntype: competitor\nticker: XYZ\n---\n\n# X\n")
    assert parse_competitors(tmp_path) == []
