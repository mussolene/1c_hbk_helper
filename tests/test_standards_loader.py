"""Tests for standards_loader."""

import io
import zipfile
from pathlib import Path
from unittest.mock import patch

from onec_help.standards_loader import collect_from_folder, fetch_repo_archive


def test_collect_from_folder_md(tmp_path: Path) -> None:
    """Collect *.md files with title from heading."""
    (tmp_path / "rule1.md").write_text(
        "# Проверка транзакций\n\nПосле начала транзакции нужен блок Попытка-Исключение.",
        encoding="utf-8",
    )
    items = collect_from_folder(tmp_path)
    assert len(items) == 1
    assert items[0]["title"] == "Проверка транзакций"
    assert "транзакции" in items[0]["description"] or "Попытка" in items[0]["description"]
    assert "code_snippet" in items[0]


def test_collect_skips_readme(tmp_path: Path) -> None:
    """README.md is skipped."""
    (tmp_path / "README.md").write_text("# Doc\n\nContent", encoding="utf-8")
    assert collect_from_folder(tmp_path) == []


def test_collect_empty(tmp_path: Path) -> None:
    """Empty folder returns empty list."""
    assert collect_from_folder(tmp_path) == []


def test_fetch_repo_archive(tmp_path: Path) -> None:
    """fetch_repo_archive extracts zip and returns (subpath_dir, temp_dir)."""
    # Create minimal zip: repo-master/docs/rule.md
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("v8-code-style-master/docs/rule.md", "# Имя переменной\n\nОписание.")
    buf.seek(0)
    data = buf.getvalue()

    def fake_urlopen(*args, **kwargs):
        return io.BytesIO(data)

    with patch("onec_help.standards_loader.urlopen", side_effect=fake_urlopen):
        target, temp_dir = fetch_repo_archive(
            "https://github.com/1C-Company/v8-code-style", subpath="docs"
        )
    assert target.is_dir()
    assert (target / "rule.md").exists()
    items = collect_from_folder(target)
    assert len(items) == 1
    assert "Имя переменной" in items[0]["title"]
    import shutil

    shutil.rmtree(temp_dir, ignore_errors=True)
