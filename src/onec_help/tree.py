"""Build tree for web UI (file/folder tree with html_path)."""

import uuid
from pathlib import Path
from typing import Any


def build_tree(directory):
    """
    Build a tree structure from directory contents for the web viewer.
    Each node: id, identifier, html_path, is_folder, children, parent_id, image_index.
    """
    directory = Path(directory).resolve()
    flat: list[dict[str, Any]] = []

    def walk_dir(dir_path: Path, parent_id=None) -> None:
        for item in sorted(dir_path.iterdir()):
            node_id = str(uuid.uuid4())
            html_path = None
            if item.is_file() and item.suffix == ".html":
                html_path = str(item.relative_to(directory))
            element = {
                "id": node_id,
                "identifier": item.name,
                "html_path": html_path,
                "is_folder": item.is_dir(),
                "children": [],
                "parent_id": parent_id,
                "image_index": 0 if item.is_dir() else 2,
            }
            if parent_id:
                parent = next((e for e in flat if e["id"] == parent_id), None)
                if parent:
                    parent["children"].append(element)
            else:
                flat.append(element)
            if item.is_file() and item.suffix == ".html":
                folder_path = item.parent / item.stem
                if folder_path.is_dir():
                    walk_dir(folder_path, node_id)
            if item.is_dir():
                walk_dir(item, node_id)

    walk_dir(directory)
    return flat


def _path_inside_base(path: Path, base: Path) -> bool:
    """Return True if path resolves to a location under base (prevents path traversal)."""
    try:
        resolved = path.resolve()
        base_resolved = base.resolve()
        return resolved.is_relative_to(base_resolved) or resolved == base_resolved
    except (ValueError, OSError):
        return False


def get_html_content(html_path: str, base_dir) -> str:
    """Read HTML file and adjust links for web serving (href -> /content/, src -> /download/)."""
    base = Path(base_dir).resolve()
    file_path = (base / html_path).resolve()
    if not _path_inside_base(file_path, base):
        return "<html><body>No content available</body></html>"
    if not file_path.exists() or file_path.suffix != ".html":
        return "<html><body>No content available</body></html>"
    from .html2md import read_file_with_encoding_fallback

    content = read_file_with_encoding_fallback(file_path)
    content = content.replace('href="', 'href="/content/').replace('src="', 'src="/download/')
    return content
