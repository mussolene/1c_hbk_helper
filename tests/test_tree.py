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


def test_get_html_content_non_html_suffix(tmp_path: Path) -> None:
    """Non-.html path returns default message."""
    (tmp_path / "readme.txt").write_text("text")
    content = get_html_content("readme.txt", tmp_path)
    assert "No content" in content


def test_build_tree_with_html_and_same_name_folder(tmp_path: Path) -> None:
    """When an .html file has a same-name folder, walk_dir recurses into it."""
    (tmp_path / "page.html").write_text("<html></html>")
    (tmp_path / "page").mkdir()
    (tmp_path / "page" / "nested.html").write_text("<html><body>Nested</body></html>")
    nodes = build_tree(tmp_path)
    root = next(n for n in nodes if n["identifier"] == "page.html")
    assert root is not None
    assert root["html_path"] == "page.html"
    children = root.get("children") or []
    nested = next((c for c in children if c["identifier"] == "nested.html"), None)
    assert nested is not None
    assert "nested.html" in (nested.get("html_path") or "")
