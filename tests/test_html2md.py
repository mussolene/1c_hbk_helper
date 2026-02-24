"""Tests for html2md module."""
import pytest
from pathlib import Path

from onec_help.html2md import html_to_md_content, build_docs


def test_html_to_md_content(sample_html: Path) -> None:
    md = html_to_md_content(sample_html)
    assert md
    assert "# " in md
    assert "Имя общего реквизита" in md or "реквизит" in md.lower()


def test_html_to_md_content_missing() -> None:
    assert html_to_md_content(Path("/nonexistent")) == ""


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
