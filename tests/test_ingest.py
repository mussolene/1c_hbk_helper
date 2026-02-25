"""Tests for ingest module: collect tasks, discover versions, parse env, run_ingest (dry_run / empty)."""
from pathlib import Path
from unittest.mock import MagicMock, patch

from onec_help.ingest import (
    _language_from_filename,
    collect_hbk_tasks,
    discover_version_dirs,
    parse_languages_env,
    parse_source_dirs_env,
    run_ingest,
    run_unpack_only,
)


def test_language_from_filename() -> None:
    assert _language_from_filename("1cv8_ru.hbk") == "ru"
    assert _language_from_filename("shcntx_en.HBK") == "en"
    assert _language_from_filename("other.hbk") is None
    assert _language_from_filename("no_ext") is None


def test_collect_hbk_tasks_empty_sources() -> None:
    assert collect_hbk_tasks([], None) == []
    assert collect_hbk_tasks([], ["ru"]) == []


def test_collect_hbk_tasks_no_dir(tmp_path: Path) -> None:
    assert collect_hbk_tasks([(tmp_path / "missing", "v1")], None) == []


def test_collect_hbk_tasks_filters_language(tmp_path: Path) -> None:
    sub = tmp_path / "8.3"
    sub.mkdir()
    (sub / "1cv8_ru.hbk").write_bytes(b"x")
    (sub / "1cv8_en.hbk").write_bytes(b"y")
    tasks = collect_hbk_tasks([(tmp_path, "8.3")], ["ru"])
    paths = [t[0] for t in tasks]
    assert len(paths) == 1
    assert paths[0].name == "1cv8_ru.hbk"


def test_collect_hbk_tasks_all_languages(tmp_path: Path) -> None:
    sub = tmp_path / "v"
    sub.mkdir()
    (sub / "1cv8_ru.hbk").write_bytes(b"x")
    (sub / "1cv8_en.hbk").write_bytes(b"y")
    tasks = collect_hbk_tasks([(tmp_path, "v")], None)
    assert len(tasks) == 2
    names = {t[0].name for t in tasks}
    assert names == {"1cv8_ru.hbk", "1cv8_en.hbk"}


def test_collect_hbk_tasks_skips_no_lang(tmp_path: Path) -> None:
    sub = tmp_path / "v"
    sub.mkdir()
    (sub / "plain.hbk").write_bytes(b"x")
    tasks = collect_hbk_tasks([(tmp_path, "v")], None)
    assert len(tasks) == 0


def test_discover_version_dirs_empty(tmp_path: Path) -> None:
    assert discover_version_dirs(tmp_path) == []


def test_discover_version_dirs_ignores_files(tmp_path: Path) -> None:
    (tmp_path / "file.txt").write_text("x")
    assert discover_version_dirs(tmp_path) == []


def test_discover_version_dirs_ignores_hidden(tmp_path: Path) -> None:
    (tmp_path / ".hidden").mkdir()
    assert discover_version_dirs(tmp_path) == []


def test_discover_version_dirs_returns_subdirs(tmp_path: Path) -> None:
    (tmp_path / "8.3.27").mkdir()
    (tmp_path / "8.3.26").mkdir()
    result = discover_version_dirs(tmp_path)
    assert len(result) == 2
    names = {r[1] for r in result}
    assert names == {"8.3.27", "8.3.26"}


def test_parse_source_dirs_env_empty() -> None:
    assert parse_source_dirs_env("") == []
    assert parse_source_dirs_env(None) == []


def test_parse_source_dirs_env_path_only() -> None:
    out = parse_source_dirs_env("/opt/1cv8")
    assert out == [("/opt/1cv8", "1cv8")]


def test_parse_source_dirs_env_path_version() -> None:
    out = parse_source_dirs_env("/opt/1cv8:8.3.27")
    assert out == [("/opt/1cv8", "8.3.27")]


def test_parse_source_dirs_env_multiple() -> None:
    out = parse_source_dirs_env("/a:va,/b:vb")
    assert out == [("/a", "va"), ("/b", "vb")]


def test_parse_languages_env_empty() -> None:
    assert parse_languages_env("") is None
    assert parse_languages_env(None) is None


def test_parse_languages_env_all() -> None:
    assert parse_languages_env("all") is None


def test_parse_languages_env_single() -> None:
    assert parse_languages_env("ru") == ["ru"]


def test_parse_languages_env_multi() -> None:
    assert parse_languages_env("ru,en") == ["ru", "en"]


def test_run_ingest_dry_run(tmp_path: Path) -> None:
    (tmp_path / "v").mkdir()
    (tmp_path / "v" / "1cv8_ru.hbk").write_bytes(b"x")
    n = run_ingest(
        source_dirs_with_versions=[(tmp_path, "v")],
        languages=["ru"],
        temp_base=tmp_path / "temp",
        dry_run=True,
        verbose=True,
    )
    assert n == 0


def test_run_ingest_empty_sources() -> None:
    n = run_ingest(
        source_dirs_with_versions=[],
        temp_base="/tmp/help_ingest",
    )
    assert n == 0


def test_run_ingest_no_tasks(tmp_path: Path) -> None:
    (tmp_path / "v").mkdir()
    # no .hbk files
    n = run_ingest(
        source_dirs_with_versions=[(tmp_path, "v")],
        languages=["ru"],
        temp_base=tmp_path / "temp",
    )
    assert n == 0


def test_run_unpack_only_empty(tmp_path: Path) -> None:
    n = run_unpack_only(
        source_dirs_with_versions=[],
        output_dir=tmp_path,
        verbose=False,
    )
    assert n == 0


def test_run_unpack_only_no_tasks(tmp_path: Path) -> None:
    (tmp_path / "v").mkdir()
    n = run_unpack_only(
        source_dirs_with_versions=[(tmp_path, "v")],
        output_dir=tmp_path / "out",
        languages=["ru"],
        verbose=False,
    )
    assert n == 0


@patch("onec_help.unpack.unpack_hbk")
def test_run_unpack_only_one_archive(mock_unpack: MagicMock, tmp_path: Path) -> None:
    (tmp_path / "v").mkdir()
    (tmp_path / "v" / "1cv8_ru.hbk").write_bytes(b"x")
    out = tmp_path / "output"
    n = run_unpack_only(
        source_dirs_with_versions=[(tmp_path, "v")],
        output_dir=out,
        languages=["ru"],
        max_workers=1,
        verbose=False,
    )
    assert n == 1
    mock_unpack.assert_called_once()
    call_args = mock_unpack.call_args[0]
    assert call_args[0].name == "1cv8_ru.hbk"
    assert (out / "v" / "ru" / "1cv8_ru").exists()


@patch("onec_help.indexer.build_index")
@patch("onec_help.html2md.build_docs")
@patch("onec_help.unpack.unpack_hbk")
@patch("qdrant_client.QdrantClient")
def test_run_ingest_unpack_fails_one_task(
    mock_qdrant: MagicMock,
    mock_unpack: MagicMock,
    mock_build_docs: MagicMock,
    mock_build_index: MagicMock,
    tmp_path: Path,
) -> None:
    """When unpack raises, task is skipped and no index call for that task."""
    (tmp_path / "v").mkdir()
    (tmp_path / "v" / "1cv8_ru.hbk").write_bytes(b"x")
    mock_unpack.side_effect = RuntimeError("7z failed")
    mock_qdrant.return_value.collection_exists.return_value = True
    n = run_ingest(
        source_dirs_with_versions=[(tmp_path, "v")],
        languages=["ru"],
        temp_base=tmp_path / "temp",
        max_workers=1,
        verbose=False,
    )
    assert n == 0
    mock_build_index.assert_not_called()


@patch("onec_help.indexer.build_index")
@patch("onec_help.html2md.build_docs")
@patch("onec_help.unpack.unpack_hbk")
@patch("qdrant_client.QdrantClient")
def test_run_ingest_integration_mock(
    mock_qdrant: MagicMock,
    mock_unpack: MagicMock,
    mock_build_docs: MagicMock,
    mock_build_index: MagicMock,
    tmp_path: Path,
) -> None:
    """Run ingest with one .hbk; unpack and build_docs succeed; index is called."""
    (tmp_path / "v").mkdir()
    hbk = tmp_path / "v" / "1cv8_ru.hbk"
    hbk.write_bytes(b"x")
    md_dir = tmp_path / "temp" / "v" / "ru" / "1cv8_ru" / "md"
    md_dir.mkdir(parents=True)
    (md_dir / "one.md").write_text("# One\n\nBody.", encoding="utf-8")
    mock_build_docs.side_effect = lambda src, out: (out / "one.md").write_text("# One\n\nBody.", encoding="utf-8")

    mock_build_index.return_value = 1
    mock_qdrant.return_value.collection_exists.return_value = False

    n = run_ingest(
        source_dirs_with_versions=[(tmp_path, "v")],
        languages=["ru"],
        temp_base=tmp_path / "temp",
        qdrant_host="localhost",
        qdrant_port=6333,
        max_workers=1,
        verbose=False,
    )
    assert mock_unpack.called
    assert mock_build_index.return_value == 1
    assert n >= 1
