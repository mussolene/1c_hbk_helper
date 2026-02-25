"""Tests for html2md module."""
from pathlib import Path

from onec_help.html2md import (
    _looks_like_html,
    _normalize_md_text,
    _read_html_file,
    build_docs,
    html_to_md_content,
)


def test_normalize_md_text() -> None:
    """HTML entities and Unicode are normalized for consistent display and search."""
    assert _normalize_md_text("a&amp;b") == "a&b"
    assert _normalize_md_text("&nbsp;") == "\u00a0"
    assert _normalize_md_text("&lt;tag&gt;") == "<tag>"
    assert _normalize_md_text("&#1057;&#1080;&#1085;&#1090;&#1072;&#1082;&#1089;&#1080;&#1089;") == "Синтаксис"
    assert _normalize_md_text("plain") == "plain"
    assert _normalize_md_text("") == ""


def test_html_to_md_content(sample_html: Path) -> None:
    md = html_to_md_content(sample_html)
    assert md
    assert "# " in md
    assert "Имя общего реквизита" in md or "реквизит" in md.lower()


def test_html_to_md_content_missing() -> None:
    assert html_to_md_content(Path("/nonexistent")) == ""


def test_read_html_file_utf8(tmp_path: Path) -> None:
    f = tmp_path / "a.html"
    f.write_text("<html><body>Test</body></html>", encoding="utf-8")
    assert "Test" in _read_html_file(f)


def test_read_html_file_cp1251(tmp_path: Path) -> None:
    """Legacy 1C help may be in cp1251."""
    f = tmp_path / "c.html"
    f.write_bytes("<html><body>".encode("utf-8") + "Русский".encode("cp1251") + b"</body></html>")
    text = _read_html_file(f)
    assert "Русский" in text


def test_read_html_file_fallback_replace(tmp_path: Path) -> None:
    """When no encoding works, decode with errors=replace."""
    f = tmp_path / "d.html"
    f.write_bytes(b"<html>\xff\xfe</html>")
    text = _read_html_file(f)
    assert "<html>" in text
    assert "\ufffd" in text or "html" in text


def test_looks_like_html(tmp_path: Path) -> None:
    html_file = tmp_path / "f.html"
    html_file.write_text("<html><body>x</body></html>", encoding="utf-8")
    assert _looks_like_html(html_file) is True
    bin_file = tmp_path / "f.bin"
    bin_file.write_bytes(b"\x00\x01\x02")
    assert _looks_like_html(bin_file) is False


def test_build_docs_empty_dir(tmp_path: Path) -> None:
    """Empty dir yields no .md files."""
    out = tmp_path / "out"
    out.mkdir()
    created = build_docs(tmp_path, out)
    assert created == []


def test_build_docs(help_sample_dir: Path, tmp_path: Path) -> None:
    created = build_docs(help_sample_dir, tmp_path)
    assert len(created) >= 1
    assert all(p.suffix == ".md" for p in created)
    content = created[0].read_text(encoding="utf-8")
    assert content.strip().startswith("#")


def test_html_to_md_with_sections(help_sample_dir: Path) -> None:
    fn = help_sample_dir / "function_sample.html"
    if fn.exists():
        md = html_to_md_content(fn)
        assert "Формат" in md
        assert "Описание" in md or "Синтаксис" in md
        assert "Параметры" in md or "Значение" in md


def test_function_sample_md_structure(help_sample_dir: Path) -> None:
    """V8SH article must yield formal MD: title + sections Описание, Синтаксис, Параметры, Пример, См. также."""
    fn = help_sample_dir / "function_sample.html"
    if not fn.exists():
        return
    md = html_to_md_content(fn)
    assert md.startswith("# "), "MD must start with level-1 heading"
    assert "## Описание" in md
    assert "## Синтаксис" in md
    assert "## Параметры" in md
    assert "## Пример" in md
    assert "## См. также" in md
    assert "Формат(Значение, ФорматнаяСтрока)" in md or "Формат" in md
    assert "Значение" in md and "ФорматнаяСтрока" in md
