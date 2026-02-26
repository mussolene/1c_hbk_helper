"""Tests for snippets_loader."""

from pathlib import Path

import pytest

from onec_help.snippets_loader import collect_from_folder


def test_collect_from_folder_bsl(tmp_path: Path) -> None:
    """Collect *.bsl files."""
    (tmp_path / "a.bsl").write_text("Сообщить(1);", encoding="utf-8")
    items = collect_from_folder(tmp_path)
    assert len(items) == 1
    assert items[0]["title"] == "a"
    assert items[0]["code_snippet"] == "Сообщить(1);"


def test_collect_from_folder_1c(tmp_path: Path) -> None:
    """Collect *.1c files."""
    (tmp_path / "b.1c").write_text("Возврат Истина;", encoding="utf-8")
    items = collect_from_folder(tmp_path)
    assert len(items) == 1
    assert items[0]["title"] == "b"


def test_collect_from_folder_md_with_frontmatter(tmp_path: Path) -> None:
    """Collect *.md with YAML frontmatter and code block."""
    (tmp_path / "c.md").write_text(
        "---\ntitle: Мой пример\ndescription: Тест\n---\n\n```bsl\nСообщить(2);\n```",
        encoding="utf-8",
    )
    items = collect_from_folder(tmp_path)
    assert len(items) == 1
    assert items[0]["title"] == "Мой пример"
    assert items[0]["description"] == "Тест"
    assert "Сообщить(2)" in items[0]["code_snippet"]


def test_collect_from_folder_skips_readme(tmp_path: Path) -> None:
    """README.md is skipped."""
    (tmp_path / "README.md").write_text("```bsl\nx\n```", encoding="utf-8")
    items = collect_from_folder(tmp_path)
    assert len(items) == 0


def test_collect_from_folder_empty(tmp_path: Path) -> None:
    """Empty folder returns empty list."""
    assert collect_from_folder(tmp_path) == []
