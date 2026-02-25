"""
Ingest .hbk from multiple read-only source directories.
Unpacks to a temp dir in the container, builds docs, indexes with version/language, then cleans up.
Supports language filter (e.g. only *_ru.hbk) and concurrent processing.
Progress is printed to stderr so long runs are not killed by "no output" timeouts.
"""

import os
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, List, Optional, Tuple, Union

def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)

# Language: filename pattern like 1cv8_ru.hbk, shcntx_en.hbk
LANG_PATTERN = re.compile(r"_([a-z]{2})\.hbk$", re.IGNORECASE)


def _language_from_filename(name: str) -> Optional[str]:
    m = LANG_PATTERN.search(name)
    return m.group(1).lower() if m else None


def collect_hbk_tasks(
    source_dirs_with_versions: list[tuple[Path, str]],
    languages: Optional[List[str]],
) -> List[Tuple[Path, str, str]]:
    """
    Scan source dirs (read-only) for .hbk files. Each item: (source_dir, version_label).
    Поиск рекурсивный (rglob), в т.ч. в подпапке bin/ (типично для Windows:
    C:\\Program Files\\1cv8\\8.3.27.1859\\bin).
    languages: e.g. ["ru"] for only *_ru.hbk; None or [] = all languages.
    Returns list of (hbk_path, version, language).
    """
    tasks: List[Tuple[Path, str, str]] = []
    for source_dir, version in source_dirs_with_versions:
        source_dir = Path(source_dir).resolve()
        if not source_dir.is_dir():
            continue
        for path in source_dir.rglob("*.hbk"):
            if not path.is_file():
                continue
            lang = _language_from_filename(path.name)
            if lang is None:
                continue
            if languages and lang not in [l.lower() for l in languages]:
                continue
            tasks.append((path, version, lang))
    return tasks


def _unpack_and_build_docs(
    hbk_path: Path,
    version: str,
    language: str,
    temp_base: Path,
    unpack_fn: Any,
    build_docs_fn: Any,
) -> Tuple[Optional[Path], str, str, Optional[str]]:
    """Unpack one .hbk to temp, build .md there. Returns (md_dir, version, language, error_message) or (None, v, l, reason) on failure."""
    safe_name = re.sub(r"[^\w\-]", "_", hbk_path.stem)
    out_sub = temp_base / version / language / safe_name
    unpacked = out_sub / "unpacked"
    md_dir = out_sub / "md"
    err_msg: Optional[str] = None
    try:
        unpacked.mkdir(parents=True, exist_ok=True)
        unpack_fn(hbk_path, unpacked)
        md_dir.mkdir(parents=True, exist_ok=True)
        build_docs_fn(unpacked, md_dir)
        if any(md_dir.rglob("*.md")) or any(md_dir.rglob("*")) and not list(md_dir.rglob("*.md")):
            # build_docs may create .md or we have extension-less HTML; indexer will use HTML fallback
            return (md_dir, version, language, None)
        return (md_dir, version, language, None)
    except Exception as e:
        err_msg = f"{type(e).__name__}: {e}"
        return (None, version, language, err_msg)
    finally:
        if unpacked.exists():
            try:
                shutil.rmtree(unpacked)
            except OSError:
                pass


def run_ingest(
    source_dirs_with_versions: List[Tuple[Union[Path, str], str]],
    languages: Optional[List[str]] = None,
    temp_base: Optional[Union[Path, str]] = None,
    qdrant_host: str = "localhost",
    qdrant_port: int = 6333,
    collection: str = "onec_help",
    incremental: bool = True,
    max_workers: int = 4,
    max_tasks: Optional[int] = None,
    verbose: bool = True,
    dry_run: bool = False,
    index_batch_size: int = 500,
) -> int:
    """
    Ingest .hbk from multiple source dirs (read-only): unpack to temp, build docs, index in batches, cleanup.
    source_dirs_with_versions: [(path, version_label), ...].
    languages: e.g. ["ru"] for only *_ru.hbk; None or [] = all.
    temp_base: dir inside container for unpack (default /tmp/help_ingest). Removed at end.
    max_tasks: if set, process only first N .hbk files (for resumable runs or to avoid timeout).
    verbose: print progress to stderr (keeps long runs from being killed by "no output" timeouts).
    dry_run: if True, only report how many .hbk tasks would be processed and return 0.
    index_batch_size: number of files per index upsert (smaller = more progress, less memory per step).
    Returns total points indexed (0 if dry_run).
    """
    from .unpack import unpack_hbk
    from .html2md import build_docs
    from .indexer import build_index, VECTOR_SIZE
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams

    if not source_dirs_with_versions:
        return 0

    base = Path(temp_base or "/tmp/help_ingest").resolve()
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise RuntimeError(f"Cannot create temp dir {base}: {e}") from e

    pairs = [(Path(p).resolve(), v) for p, v in source_dirs_with_versions]
    tasks = collect_hbk_tasks(pairs, languages)
    if not tasks:
        return 0

    if dry_run:
        if verbose:
            _log(f"[ingest] DRY RUN: would process {len(tasks)} .hbk task(s)")
            for i, (path, version, lang) in enumerate(tasks[: 25], 1):
                _log(f"  {i}. {version}/{lang}  {path.name}")
            if len(tasks) > 25:
                _log(f"  ... and {len(tasks) - 25} more")
        return 0

    if max_tasks is not None and max_tasks > 0:
        tasks = tasks[: max_tasks]
        if verbose:
            _log(f"[ingest] Limiting to first {max_tasks} task(s)")

    if verbose:
        _log(f"[ingest] Found {len(tasks)} .hbk task(s); workers={max_workers}")

    # Ensure collection exists once (avoid race when multiple workers call build_index)
    if incremental:
        client = QdrantClient(host=qdrant_host, port=qdrant_port, check_compatibility=False)
        if not client.collection_exists(collection):
            client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            )
            if verbose:
                _log("[ingest] Created Qdrant collection")

    total_indexed = 0
    done = 0
    failed: List[Tuple[Path, str, str, str]] = []  # (path, version, language, error_message)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _unpack_and_build_docs,
                path,
                version,
                lang,
                base,
                unpack_hbk,
                build_docs,
            ): (path, version, lang)
            for path, version, lang in tasks
        }
        for future in as_completed(futures):
            path_hbk, version, language = futures[future]
            done += 1
            md_dir, _, _, err_msg = future.result()
            if md_dir is None or not md_dir.exists():
                reason = (err_msg or "unknown").split("\n")[0].strip()[:200]
                failed.append((path_hbk, version, language, err_msg or "unknown"))
                if verbose:
                    _log(f"[ingest] [{done}/{len(tasks)}] skip (unpack/build failed) {version}/{language} — {path_hbk}")
                    _log(f"[ingest]   reason: {reason}")
                continue
            try:
                if verbose:
                    _log(f"[ingest] [{done}/{len(tasks)}] indexing {version}/{language} — {path_hbk}")
                n = build_index(
                    docs_dir=md_dir,
                    qdrant_host=qdrant_host,
                    qdrant_port=qdrant_port,
                    collection=collection,
                    incremental=incremental,
                    extra_payload={"version": version, "language": language},
                    batch_size=index_batch_size,
                )
                total_indexed += n
                if verbose:
                    _log(f"[ingest] [{done}/{len(tasks)}] indexed {n} points ({version}/{language}) — {path_hbk}, total={total_indexed}")
            finally:
                try:
                    shutil.rmtree(md_dir.parent)
                except OSError:
                    pass
    try:
        shutil.rmtree(base)
    except OSError:
        pass
    if verbose:
        _log(f"[ingest] Done. Total points indexed: {total_indexed}")
    if failed and verbose:
        _log(f"[ingest] Failed {len(failed)} file(s) (unpack or build_docs error):")
        for path_hbk, version, language, err in failed:
            short_err = (err or "").split("\n")[0].strip()[:150]
            _log(f"[ingest]   — {version}/{language} {path_hbk.name}: {short_err}")
        fail_log = os.environ.get("INGEST_FAILED_LOG")
        if fail_log:
            try:
                with open(fail_log, "w", encoding="utf-8") as f:
                    f.write(f"# Ingest failed .hbk ({len(failed)})\n")
                    for path_hbk, version, language, err in failed:
                        f.write(f"{version}\t{language}\t{path_hbk}\t{err or ''}\n")
                _log(f"[ingest] Wrote failure list to {fail_log}")
            except OSError as e:
                _log(f"[ingest] Could not write failure log {fail_log}: {e}")
    return total_indexed


def _unpack_one(
    path: Path,
    version: str,
    lang: str,
    output_base: Path,
    unpack_fn: Any,
    verbose: bool,
) -> Tuple[bool, str]:
    """Unpack one .hbk. Returns (success, message)."""
    safe_name = re.sub(r"[^\w\-]", "_", path.stem)
    out_sub = output_base / version / lang / safe_name
    try:
        out_sub.mkdir(parents=True, exist_ok=True)
        unpack_fn(path, out_sub)
        msg = f"{version}/{lang} → {out_sub.relative_to(output_base)}"
        if verbose:
            _log(f"[unpack] {msg}")
        return (True, msg)
    except Exception as e:
        if verbose:
            _log(f"[unpack] skip {path}: {e}")
        return (False, str(e))


def run_unpack_only(
    source_dirs_with_versions: List[Tuple[Union[Path, str], str]],
    output_dir: Union[Path, str],
    languages: Optional[List[str]] = None,
    max_workers: int = 4,
    verbose: bool = True,
) -> int:
    """
    Only unpack .hbk files into output_dir (no build-docs, no indexing).
    Structure: output_dir / version / language / safe_stem / (unpacked files).
    Returns number of .hbk archives unpacked.
    """
    from .unpack import unpack_hbk

    output_base = Path(output_dir).resolve()
    pairs = [(Path(p).resolve(), v) for p, v in source_dirs_with_versions]
    tasks = collect_hbk_tasks(pairs, languages)
    if not tasks:
        return 0
    count = 0
    if max_workers <= 1:
        for path, version, lang in tasks:
            ok, _ = _unpack_one(path, version, lang, output_base, unpack_hbk, verbose)
            if ok:
                count += 1
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futs = [
                executor.submit(_unpack_one, path, version, lang, output_base, unpack_hbk, verbose)
                for path, version, lang in tasks
            ]
            for fut in as_completed(futs):
                ok, _ = fut.result()
                if ok:
                    count += 1
    return count


def discover_version_dirs(base_path: Union[Path, str]) -> List[Tuple[Path, str]]:
    """
    Сканировать базовый каталог: каждая прямая подпапка = версия 1С.
    Возвращает [(путь_к_подпапке, имя_подпапки), ...]. Скрытые и не-каталоги пропускаются.
    На Windows каталоги версий часто имеют вид ...\\8.3.27.1859\\bin — поиск .hbk идёт
    рекурсивно (rglob), так что файлы в bin/ находятся автоматически.
    """
    base = Path(base_path).resolve()
    if not base.is_dir():
        return []
    out: List[Tuple[Path, str]] = []
    for child in sorted(base.iterdir()):
        if child.name.startswith(".") or not child.is_dir():
            continue
        out.append((child, child.name))
    return out


def parse_source_dirs_env(env_value: Optional[str]) -> List[Tuple[str, str]]:
    """
    Parse HELP_SOURCE_DIRS (legacy): "path1:version1,path2:version2" or "path1,path2".
    Returns [(path, version), ...]. Prefer HELP_SOURCE_BASE instead.
    """
    if not env_value or not env_value.strip():
        return []
    out = []
    for part in env_value.strip().split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            p, v = part.split(":", 1)
            out.append((p.strip(), v.strip()))
        else:
            p = part
            v = Path(p).name or "default"
            out.append((p, v))
    return out


def parse_languages_env(env_value: Optional[str]) -> Optional[List[str]]:
    """
    Parse HELP_LANGUAGES: "ru" => ["ru"], "ru,en" => ["ru","en"], empty or "all" => None (all languages).
    """
    if not env_value or not env_value.strip():
        return None
    raw = env_value.strip().lower()
    if raw == "all":
        return None
    return [s.strip() for s in raw.split(",") if s.strip()]
