"""Tests for categories module."""
import pytest
from pathlib import Path

from onec_help.categories import (
    parse_content_file,
    extract_html_title,
    build_tree,
    find_categories_root,
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
