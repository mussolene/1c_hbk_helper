"""Tests for categories module."""

from pathlib import Path

from onec_help.categories import (
    build_tree,
    extract_html_title,
    find_categories_root,
    parse_content_file,
)


def test_parse_content_file(categories_file: Path) -> None:
    structure = parse_content_file(categories_file)
    assert isinstance(structure, list)
    assert "field626.html" in structure
    assert "Node573.html" in structure


def test_parse_content_file_missing() -> None:
    assert parse_content_file(Path("/nonexistent")) == []


def test_extract_html_title(sample_html: Path) -> None:
    title = extract_html_title(sample_html)
    assert "Имя общего реквизита" in title or "Common attribute" in title or title


def test_extract_html_title_missing() -> None:
    assert extract_html_title(Path("/nonexistent")) == "Untitled"


def test_extract_html_title_from_title_tag(tmp_path: Path) -> None:
    """When no h1, extract from <title>."""
    f = tmp_path / "page.html"
    f.write_text(
        "<html><head><title>Page Title Here</title></head><body></body></html>", encoding="utf-8"
    )
    assert extract_html_title(f) == "Page Title Here"


def test_build_tree(help_sample_dir: Path) -> None:
    structure = parse_content_file(help_sample_dir / "__categories__")
    tree = build_tree(help_sample_dir, structure)
    assert isinstance(tree, list)
    for node in tree:
        assert "title" in node
        assert "path" in node
        assert "children" in node


def test_find_categories_root(help_sample_dir: Path) -> None:
    root = find_categories_root(help_sample_dir)
    assert root is not None
    assert (root / "__categories__").exists()


def test_find_categories_root_not_found(tmp_path: Path) -> None:
    assert find_categories_root(tmp_path) is None


def test_build_tree_dir_without_categories(tmp_path: Path) -> None:
    """Directory without __categories__ uses iterdir() for sub structure."""
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "a.html").write_text("<html><body></body></html>", encoding="utf-8")
    structure = ["subdir"]
    tree = build_tree(tmp_path, structure)
    assert len(tree) == 1
    assert tree[0]["title"] == "subdir"
    assert "children" in tree[0]
    # One child for a.html
    assert len(tree[0]["children"]) == 1
    assert tree[0]["children"][0]["path"] == "subdir/a.html"
