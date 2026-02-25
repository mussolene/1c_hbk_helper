"""Tests for tree module."""

from pathlib import Path

from onec_help.tree import build_tree, get_html_content


def test_build_tree(help_sample_dir: Path) -> None:
    nodes = build_tree(help_sample_dir)
    assert isinstance(nodes, list)
    for n in nodes:
        assert "id" in n
        assert "identifier" in n
        assert "html_path" in n
        assert "is_folder" in n
        assert "children" in n


def test_get_html_content(help_sample_dir: Path) -> None:
    content = get_html_content("field626.html", help_sample_dir)
    assert "content" in content.lower() or "реквизит" in content.lower() or "html" in content


def test_get_html_content_missing(help_sample_dir: Path) -> None:
    content = get_html_content("nonexistent.html", help_sample_dir)
    assert "No content" in content
