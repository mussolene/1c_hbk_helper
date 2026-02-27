"""CLI: unpack, build-docs, serve, build-index, mcp."""

import argparse
import json
import os
import sys
from pathlib import Path


def _env_path(name: str, default=None):
    v = os.environ.get(name)
    if v:
        return v
    return default


def cmd_unpack(args: argparse.Namespace) -> int:
    """Unpack .hbk with 7z."""
    from .unpack import unpack_hbk

    try:
        unpack_hbk(args.archive, args.output_dir)
        print(f"Unpacked to {args.output_dir}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_build_docs(args: argparse.Namespace) -> int:
    """Generate Markdown from HTML in project dir."""
    from .html2md import build_docs

    out = args.output or Path(args.project_dir) / "docs_md"
    out = Path(out)
    try:
        created = build_docs(args.project_dir, out)
        print(f"Created {len(created)} .md files in {out}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_serve(args: argparse.Namespace) -> int:
    """Run Flask web viewer."""
    import logging

    from .web import app

    port = int(_env_path("PORT", "5000") or "5000")
    app.config["BASE_DIR"] = args.directory
    use_debug = args.debug and os.environ.get("PRODUCTION") != "1"
    if args.debug and not use_debug:
        logging.warning("PRODUCTION=1 is set; debug mode disabled for security.")
    elif use_debug:
        logging.warning("Running with debug=True. Do not use in production (exposes tracebacks).")
    app.run(host="0.0.0.0", port=port, debug=use_debug)
    return 0


def cmd_build_index(args: argparse.Namespace) -> int:
    """Build Qdrant index from Markdown (or HTML) in directory."""
    from .indexer import build_index

    docs_dir = args.docs_dir or args.directory
    try:
        count = build_index(
            docs_dir=Path(docs_dir),
            qdrant_host=os.environ.get("QDRANT_HOST", "localhost"),
            qdrant_port=int(os.environ.get("QDRANT_PORT", "6333")),
            collection=os.environ.get("QDRANT_COLLECTION", "onec_help"),
            incremental=getattr(args, "incremental", False),
            embedding_batch_size=getattr(args, "embedding_batch_size", None),
            embedding_workers=getattr(args, "embedding_workers", None),
        )
        print(f"Indexed {count} chunks")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_index_status(args: argparse.Namespace) -> int:
    """Print index status: points count, versions, languages; ingest progress (embedding speed, per-folder, ETA)."""
    from .indexer import get_index_status
    from .ingest import read_ingest_status

    host = os.environ.get("QDRANT_HOST", "localhost")
    port = int(os.environ.get("QDRANT_PORT", "6333"))
    collection = os.environ.get("QDRANT_COLLECTION", "onec_help")
    s = get_index_status(qdrant_host=host, qdrant_port=port, collection=collection)
    if s.get("error"):
        print(f"Error: {s['error']}", file=sys.stderr)
        return 1
    ingest = read_ingest_status()
    if not s.get("exists") and not ingest:
        print("Index does not exist. Run: python -m onec_help ingest")
        return 0
    if s.get("exists"):
        pts = s.get("points_count", 0)
        print(f"Collection: {s.get('collection', 'onec_help')}")
        print(f"Topics indexed: {pts}")
        print(f"Embeddings: {pts}")
        storage_path = os.environ.get("QDRANT_STORAGE_PATH")
        if storage_path and os.path.isdir(storage_path):
            try:
                total = 0
                for dirpath, _dirnames, filenames in os.walk(storage_path):
                    for f in filenames:
                        p = os.path.join(dirpath, f)
                        try:
                            total += os.path.getsize(p)
                        except OSError:
                            pass
                size_mb = total / (1024 * 1024)
                print(f"DB size: {size_mb:.1f} MB")
            except OSError:
                print("DB size: —")
        elif storage_path:
            print("DB size: — (path not found)")
        if s.get("versions"):
            print(f"Versions (sample): {', '.join(s['versions'])}")
        if s.get("languages"):
            print(f"Languages (sample): {', '.join(s['languages'])}")
    if ingest:
        backend = ingest.get("embedding_backend") or "none"
        print(f"Embedding: {backend}")
        if backend == "none":
            print("Embedding speed: none")
        else:
            speed = ingest.get("embedding_speed_pts_per_sec")
            if speed is not None:
                print(f"Embedding speed: {speed} pts/sec")
            else:
                print("Embedding speed: —")
        elapsed = ingest.get("elapsed_sec")
        if elapsed is not None:
            print(f"Elapsed: {elapsed} s")
        status = ingest.get("status", "")
        if status == "completed":
            total_sec = ingest.get("total_elapsed_sec")
            if total_sec is not None:
                print(f"Indexing finished. Total time: {total_sec} s")
            print("Indexing: completed")
        else:
            print("Indexing: in progress")
            eta = ingest.get("eta_sec")
            if eta is not None:
                print(f"ETA: ~{int(eta)} s")
        current = ingest.get("current") or []
        if current:
            print("Current (per thread):")
            for c in current:
                path = c.get("path", "")
                ver = c.get("version", "")
                lang = c.get("language", "")
                stage = c.get("stage", "")
                print(f"  {ver}/{lang}  {path}  — {stage}")
        folders = ingest.get("folders") or []
        if folders:
            print("Per folder (version/lang): hbk → html, md, err, pts")
            for fo in folders:
                v = fo.get("version", "")
                lang = fo.get("language", "")
                hbk = fo.get("hbk_count", 0)
                html = fo.get("html_count", 0)
                md = fo.get("md_count", 0)
                err = fo.get("err_count", 0)
                pts = fo.get("points", 0)
                st = fo.get("status", "pending")
                # One line: 8.3/ru  hbk:2  html:150  md:120  err:0  pts:120  done
                print(f"  {v}/{lang}  hbk:{hbk}  html:{html}  md:{md}  err:{err}  pts:{pts}  {st}")
    return 0


def cmd_unpack_dir(args: argparse.Namespace) -> int:
    """Unpack all .hbk from source dir(s) into output_dir (no indexing)."""
    import os
    from pathlib import Path

    from .ingest import (
        discover_version_dirs,
        parse_languages_env,
        parse_source_dirs_env,
        run_unpack_only,
    )

    sources: list[tuple[str, str]] = []
    if getattr(args, "sources", None):
        for s in args.sources:
            s = s.strip()
            if ":" in s:
                p, v = s.split(":", 1)
                sources.append((p.strip(), v.strip()))
            else:
                sources.append((s, Path(s).name or "default"))
    if not sources:
        base = os.environ.get("HELP_SOURCE_BASE") or os.environ.get("HELP_SOURCES_DIR")
        if base and base.strip():
            discovered = discover_version_dirs(base.strip())
            sources = [(str(p), v) for p, v in discovered]
        if not sources:
            sources = parse_source_dirs_env(os.environ.get("HELP_SOURCE_DIRS"))
    if not sources:
        # Single directory as version
        src = getattr(args, "source_dir", None) or ""
        if src and Path(src).is_dir():
            sources = [(src, Path(src).name or "default")]
    if not sources:
        print(
            "Error: no source directories. Set HELP_SOURCE_BASE or use --sources or pass source_dir",
            file=sys.stderr,
        )
        return 1
    raw_lang = getattr(args, "languages", None)
    languages = parse_languages_env(
        raw_lang if raw_lang is not None and raw_lang.strip() else os.environ.get("HELP_LANGUAGES")
    )
    out = Path(args.output_dir or "./unpacked").resolve()
    try:
        n = run_unpack_only(
            source_dirs_with_versions=sources,
            output_dir=out,
            languages=languages,
            max_workers=getattr(args, "workers", 4),
            verbose=not getattr(args, "quiet", False),
        )
        print(f"Unpacked {n} archive(s) to {out}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_ingest(args: argparse.Namespace) -> int:
    """Ingest .hbk from multiple read-only source dirs: unpack to temp, build docs, index, cleanup."""
    from pathlib import Path

    from .ingest import (
        discover_version_dirs,
        parse_languages_env,
        parse_source_dirs_env,
        run_ingest,
    )

    sources: list[tuple[str, str]] = []
    if getattr(args, "sources", None):
        for s in args.sources:
            s = s.strip()
            if ":" in s:
                p, v = s.split(":", 1)
                sources.append((p.strip(), v.strip()))
            else:
                sources.append((s, Path(s).name or "default"))
    if not sources and getattr(args, "sources_file", None):
        # sources_file path is from CLI args; CLI is intended for trusted operator use only
        for line in Path(args.sources_file).read_text(encoding="utf-8").strip().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                p, v = line.split(":", 1)
                sources.append((p.strip(), v.strip()))
            else:
                sources.append((line, Path(line).name or "default"))
    if not sources:
        base = os.environ.get("HELP_SOURCE_BASE") or os.environ.get("HELP_SOURCES_DIR")
        if base and base.strip():
            discovered = discover_version_dirs(base.strip())
            sources = [(str(p), v) for p, v in discovered]
        if not sources:
            sources = parse_source_dirs_env(os.environ.get("HELP_SOURCE_DIRS"))
    if not sources:
        print(
            "Error: no source directories. Set HELP_SOURCE_BASE (path to folder with version subdirs) or use --sources / --sources-file",
            file=sys.stderr,
        )
        return 1
    raw_lang = getattr(args, "languages", None)
    if raw_lang is not None:
        languages = parse_languages_env(raw_lang if raw_lang.strip() else "all")
    else:
        languages = parse_languages_env(os.environ.get("HELP_LANGUAGES"))
    if getattr(args, "no_cache", False):
        os.environ["INGEST_SKIP_CACHE"] = "1"
    try:
        n = run_ingest(
            source_dirs_with_versions=sources,
            languages=languages,
            temp_base=args.temp_base or os.environ.get("HELP_INGEST_TEMP", "/tmp/help_ingest"),
            qdrant_host=os.environ.get("QDRANT_HOST", "localhost"),
            qdrant_port=int(os.environ.get("QDRANT_PORT", "6333")),
            collection=os.environ.get("QDRANT_COLLECTION", "onec_help"),
            incremental=not getattr(args, "recreate", False),
            max_workers=getattr(args, "workers", None),
            max_tasks=getattr(args, "max_tasks", None),
            verbose=not getattr(args, "quiet", False),
            dry_run=getattr(args, "dry_run", False),
            index_batch_size=getattr(args, "index_batch_size", 500),
            embedding_batch_size=getattr(args, "embedding_batch_size", None),
            embedding_workers=getattr(args, "embedding_workers", None),
        )
        print(f"Ingested and indexed {n} chunks")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_load_snippets(args: argparse.Namespace) -> int:
    """Load curated snippets from JSON and/or folder into onec_help_memory (domain=snippets).
    Sources: explicit path arg, or SNIPPETS_DIR env. docs/snippets/ — только примеры, не загружаются."""
    path_arg = getattr(args, "snippets_file", None) or os.environ.get(
        "SNIPPETS_JSON_PATH", ""
    )
    snippets_dir = os.environ.get("SNIPPETS_DIR", "")

    items: list[dict] = []

    def _load_json(p: Path) -> None:
        raw = p.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, list):
            raise ValueError("JSON must be an array of {title, description, code_snippet}")
        items.extend(data)

    def _load_folder(d: Path, per_func: bool = False) -> None:
        from .snippets_loader import collect_from_folder
        items.extend(collect_from_folder(d, per_function=per_func))

    from_project = getattr(args, "from_project", None)

    try:
        if from_project:
            d = Path(from_project.strip())
            if not d.exists() or not d.is_dir():
                print(f"Error: --from-project path not found or not a directory: {d}", file=sys.stderr)
                return 1
            _load_folder(d, per_func=getattr(args, "per_function", False))
        elif path_arg and path_arg.strip():
            p = Path(path_arg.strip())
            if not p.exists():
                print(f"Error: path not found: {p}", file=sys.stderr)
                return 1
            if p.is_dir():
                for j in sorted(p.glob("*.json")):
                    _load_json(j)
                _load_folder(p, per_func=getattr(args, "per_function", False))
            else:
                _load_json(p)
        elif snippets_dir:
            d = Path(snippets_dir)
            if not d.exists():
                print(f"SNIPPETS_DIR not found: {d}", file=sys.stderr)
                return 0
            for j in sorted(d.glob("*.json")):
                _load_json(j)
            _load_folder(d, per_func=getattr(args, "per_function", False))
        else:
            print(
                "No source: set SNIPPETS_DIR, pass path, or use --from-project. docs/snippets/ — examples only.",
                file=sys.stderr,
            )
            return 0

        if not items:
            print("No snippets to load.", file=sys.stderr)
            return 0

        from ._utils import progress_done, progress_line
        from .memory import get_memory_store

        def _progress(loaded: int, tot: int, skipped: int) -> None:
            progress_line(
                f"load-snippets │ {loaded + skipped}/{tot} │ {loaded} loaded │ {skipped} skip"
            )

        store = get_memory_store()
        n = store.upsert_curated_snippets(items, progress_callback=_progress)
        progress_done(f"load-snippets │ ✓ {n} loaded → onec_help_memory")
        return 0
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_load_standards(args: argparse.Namespace) -> int:
    """Load v8-code-style standards (markdown) into onec_help_memory (domain=standards).
    Source: path arg, STANDARDS_DIR (mounted volume), or STANDARDS_REPO (auto-download, temp, delete)."""
    path_arg = getattr(args, "standards_path", None) or os.environ.get("STANDARDS_DIR", "")
    path_arg = (path_arg or "").strip()
    standards_repo = os.environ.get("STANDARDS_REPO", "").strip()
    standards_subpath = os.environ.get("STANDARDS_SUBPATH", "docs").strip() or "docs"
    standards_branch = os.environ.get("STANDARDS_BRANCH", "master").strip() or "master"
    temp_dir = None

    if path_arg:
        d = Path(path_arg)
        if not d.exists() or not d.is_dir():
            print(f"Error: path not found or not a directory: {d}", file=sys.stderr)
            return 1
    elif standards_repo:
        try:
            from .standards_loader import fetch_repo_archive

            d, temp_dir = fetch_repo_archive(
                standards_repo, subpath=standards_subpath, branch=standards_branch
            )
        except Exception as e:
            print(f"Error fetching {standards_repo}: {e}", file=sys.stderr)
            return 1
    else:
        print(
            "No source: set STANDARDS_REPO (e.g. https://github.com/1C-Company/v8-code-style) "
            "or STANDARDS_DIR / pass path.",
            file=sys.stderr,
        )
        return 0

    try:
        from ._utils import progress_done, progress_line
        from .memory import get_memory_store
        from .standards_loader import collect_from_folder

        items = collect_from_folder(d)
        if not items:
            print(f"No .md files in {d}", file=sys.stderr)
            return 0

        def _progress(loaded: int, tot: int, skipped: int) -> None:
            progress_line(
                f"load-standards │ {loaded + skipped}/{tot} │ {loaded} loaded │ {skipped} skip"
            )

        store = get_memory_store()
        n = store.upsert_curated_snippets(
            items, progress_callback=_progress, domain="standards"
        )
        progress_done(f"load-standards │ ✓ {n} loaded → onec_help_memory (domain=standards)")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        if temp_dir is not None:
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)


def cmd_parse_fastcode(args: argparse.Namespace) -> int:
    """Parse FastCode templates into snippets JSON."""
    from .parse_fastcode import run_parse

    if "-" in args.pages:
        lo, hi = args.pages.split("-", 1)
        pages = list(range(int(lo), int(hi) + 1))
    else:
        pages = [int(p) for p in args.pages.split(",")]

    out_path = args.out
    if not out_path:
        snippets_dir = os.environ.get("SNIPPETS_DIR", "")
        if snippets_dir:
            out_path = str(Path(snippets_dir) / "fastcode_snippets.json")
        else:
            out_path = "snippets/fastcode_snippets.json"
    out = Path(out_path)
    fetch_detail = not getattr(args, "no_fetch_detail", False)
    return run_parse(out=out, pages=pages, delay=args.delay, fetch_detail=fetch_detail)


def cmd_watchdog(args: argparse.Namespace) -> int:
    """Run watchdog: monitor .hbk, ingest on change; process pending memory."""
    from .watchdog import run_watchdog

    try:
        run_watchdog(
            poll_interval_sec=args.poll_interval,
            pending_interval_sec=args.pending_interval,
        )
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_mcp(args: argparse.Namespace) -> int:
    """Run MCP server (stdio, sse, http, streamable-http). Requires fastmcp (pip install fastmcp)."""
    try:
        from .mcp_server import run_mcp
    except ImportError:
        print("MCP requires fastmcp (Python 3.10+): pip install fastmcp", file=sys.stderr)
        return 1
    transport = getattr(args, "transport", None) or os.environ.get("MCP_TRANSPORT", "stdio")
    host = getattr(args, "host", None) or os.environ.get("MCP_HOST", "127.0.0.1")
    port = int(getattr(args, "port", None) or os.environ.get("MCP_PORT", "5050"))
    path = getattr(args, "path", None) or os.environ.get("MCP_PATH", "/mcp")
    try:
        run_mcp(
            help_path=Path(args.directory),
            transport=transport,
            host=host,
            port=port,
            path=path,
        )
    except RuntimeError as e:
        if "fastmcp" in str(e).lower():
            print("MCP requires fastmcp (Python 3.10+): pip install fastmcp", file=sys.stderr)
            return 1
        raise
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="onec_help", description="1C Help: unpack, docs, index, MCP"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # unpack
    p_unpack = sub.add_parser("unpack", help="Unpack .hbk with 7z")
    p_unpack.add_argument("archive", type=str, help="Path to .hbk file")
    p_unpack.add_argument(
        "--output-dir", "-o", type=str, default="./unpacked", help="Output directory"
    )
    p_unpack.set_defaults(func=cmd_unpack)

    # unpack-dir — only unpack all .hbk into a directory (no build-docs, no index)
    p_unpack_dir = sub.add_parser(
        "unpack-dir", help="Unpack all .hbk from source tree into output dir (no indexing)"
    )
    p_unpack_dir.add_argument(
        "source_dir",
        type=str,
        nargs="?",
        default="",
        help="Root dir with version subdirs (or set HELP_SOURCE_BASE)",
    )
    p_unpack_dir.add_argument(
        "--output-dir", "-o", type=str, default="./unpacked", help="Output directory"
    )
    p_unpack_dir.add_argument(
        "--sources",
        "-s",
        type=str,
        nargs="*",
        help="path:version pairs (overrides source_dir / HELP_SOURCE_BASE)",
    )
    p_unpack_dir.add_argument(
        "--languages",
        "-l",
        type=str,
        default=None,
        help="Comma-separated, e.g. ru (default: HELP_LANGUAGES or all)",
    )
    p_unpack_dir.add_argument("--workers", "-w", type=int, default=4, help="Parallel workers")
    p_unpack_dir.add_argument("--quiet", "-q", action="store_true", help="Less output")
    p_unpack_dir.set_defaults(func=cmd_unpack_dir)

    # build-docs
    p_docs = sub.add_parser("build-docs", help="Generate Markdown from HTML")
    p_docs.add_argument("project_dir", type=str, help="Directory with HTML files")
    p_docs.add_argument(
        "--output", "-o", type=str, help="Output directory (default: project_dir/docs_md)"
    )
    p_docs.set_defaults(func=cmd_build_docs)

    # serve
    p_serve = sub.add_parser("serve", help="Run web viewer")
    p_serve.add_argument("directory", type=str, help="Directory with unpacked help")
    p_serve.add_argument("--debug", action="store_true", help="Flask debug")
    p_serve.set_defaults(func=cmd_serve)

    # build-index
    p_idx = sub.add_parser("build-index", help="Build Qdrant index from Markdown/docs (recursive)")
    p_idx.add_argument("directory", type=str, help="Directory with .md or HTML")
    p_idx.add_argument("--docs-dir", type=str, help="Alias for directory (optional)")
    p_idx.add_argument(
        "--incremental",
        action="store_true",
        help="Add/update only, do not recreate collection (new files in folder will be indexed)",
    )
    p_idx.add_argument(
        "--embedding-batch-size",
        type=int,
        default=None,
        metavar="N",
        help="Texts per embedding batch (default: env EMBEDDING_BATCH_SIZE or 64)",
    )
    p_idx.add_argument(
        "--embedding-workers",
        type=int,
        default=None,
        metavar="N",
        help="Parallel API requests for openai_api (default: env EMBEDDING_WORKERS or 4)",
    )
    p_idx.set_defaults(func=cmd_build_index)

    # ingest
    p_ingest = sub.add_parser(
        "ingest", help="Ingest .hbk from multiple read-only dirs (temp unpack, index, cleanup)"
    )
    p_ingest.add_argument(
        "--sources",
        "-s",
        type=str,
        nargs="*",
        help="Alternating path:version (or set HELP_SOURCE_BASE to scan a folder of version subdirs)",
    )
    p_ingest.add_argument("--sources-file", type=str, help="File with lines: path or path:version")
    p_ingest.add_argument(
        "--languages",
        "-l",
        type=str,
        default=None,
        help="Comma-separated, e.g. ru or ru,en; default from HELP_LANGUAGES; empty=all",
    )
    p_ingest.add_argument(
        "--temp-base",
        type=str,
        default=None,
        help="Temp dir in container (default HELP_INGEST_TEMP or /tmp/help_ingest)",
    )
    p_ingest.add_argument(
        "--workers",
        "-w",
        type=int,
        default=None,
        metavar="N",
        help="Parallel workers for unpack/build (default: half of CPUs)",
    )
    p_ingest.add_argument(
        "--max-tasks",
        "-n",
        type=int,
        default=None,
        help="Process only first N .hbk files (avoids timeout; run multiple times for full index)",
    )
    p_ingest.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="No progress output (default: print progress to stderr)",
    )
    p_ingest.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report how many .hbk tasks would be processed (no unpack/index)",
    )
    p_ingest.add_argument(
        "--index-batch-size",
        type=int,
        default=500,
        metavar="N",
        help="Index N files per upsert (default 500); smaller = more progress output, less memory",
    )
    p_ingest.add_argument(
        "--recreate",
        action="store_true",
        help="Recreate Qdrant collection (e.g. after changing EMBEDDING_DIMENSION or model)",
    )
    p_ingest.add_argument(
        "--no-cache",
        action="store_true",
        help="Ignore ingest cache; re-parse and re-embed all .hbk (env INGEST_SKIP_CACHE=1)",
    )
    p_ingest.add_argument(
        "--embedding-batch-size",
        type=int,
        default=None,
        metavar="N",
        help="Texts per embedding batch (default: env EMBEDDING_BATCH_SIZE or 64)",
    )
    p_ingest.add_argument(
        "--embedding-workers",
        type=int,
        default=None,
        metavar="N",
        help="Parallel API requests for openai_api (default: env EMBEDDING_WORKERS or 4)",
    )
    p_ingest.set_defaults(func=cmd_ingest)

    # load-snippets
    p_load_snippets = sub.add_parser(
        "load-snippets",
        help="Load curated snippets from JSON and/or folder into onec_help_memory (domain=snippets)",
    )
    p_load_snippets.add_argument(
        "snippets_file",
        type=str,
        nargs="?",
        default=None,
        help="Path to snippets.json or folder (default: docs/snippets/ or SNIPPETS_JSON_PATH/SNIPPETS_DIR)",
    )
    p_load_snippets.add_argument(
        "--per-function",
        action="store_true",
        dest="per_function",
        help="Split large .bsl by procedures/functions (each as snippet, min 50 lines)",
    )
    p_load_snippets.add_argument(
        "--from-project",
        type=str,
        default=None,
        metavar="PATH",
        help="Load snippets from 1C project path (e.g. src). Uses collect_from_folder on **/*.bsl.",
    )
    p_load_snippets.set_defaults(func=cmd_load_snippets)

    # load-standards
    p_load_standards = sub.add_parser(
        "load-standards",
        help="Load v8-code-style docs (markdown) into onec_help_memory (domain=standards)",
    )
    p_load_standards.add_argument(
        "standards_path",
        type=str,
        nargs="?",
        default=None,
        help="Path to folder with .md (default: STANDARDS_DIR env)",
    )
    p_load_standards.set_defaults(func=cmd_load_standards)

    # parse-fastcode
    p_parse_fastcode = sub.add_parser(
        "parse-fastcode",
        help="Parse FastCode.im templates into snippets JSON",
    )
    p_parse_fastcode.add_argument(
        "--out",
        type=str,
        default=None,
        help="Output path (default: SNIPPETS_DIR/fastcode_snippets.json or ./snippets/fastcode_snippets.json)",
    )
    p_parse_fastcode.add_argument(
        "--pages",
        type=str,
        default="1-51",
        help="Page range, e.g. 1-51 or 1,2,3",
    )
    p_parse_fastcode.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between requests in seconds",
    )
    p_parse_fastcode.add_argument(
        "--no-fetch-detail",
        action="store_true",
        dest="no_fetch_detail",
        help="Do not fetch detail pages (faster, but code may be truncated)",
    )
    p_parse_fastcode.set_defaults(func=cmd_parse_fastcode)

    # index-status (ingest: embedding speed, per-folder, ETA, total time)
    p_status = sub.add_parser(
        "index-status",
        help="Show index status (topics, versions, languages; ingest: embedding speed, per-folder, ETA)",
    )
    p_status.set_defaults(func=cmd_index_status)

    # mcp
    p_mcp = sub.add_parser("mcp", help="Run MCP server (stdio, sse, http, streamable-http)")
    p_mcp.add_argument("directory", type=str, help="Directory with help (.md or HTML)")
    p_mcp.add_argument(
        "--transport",
        "-t",
        type=str,
        default=None,
        help="Transport: stdio (default), sse, http, streamable-http",
    )
    p_mcp.add_argument(
        "--host",
        type=str,
        default=None,
        help="Host for sse/http (default: 127.0.0.1). Use 0.0.0.0 in Docker.",
    )
    p_mcp.add_argument(
        "--port", "-p", type=int, default=None, help="Port for sse/http (default: 5050)"
    )
    p_mcp.add_argument("--path", type=str, default=None, help="URL path (default: /mcp)")
    p_mcp.set_defaults(func=cmd_mcp)

    # watchdog
    p_watchdog = sub.add_parser(
        "watchdog",
        help="Monitor new .hbk files, run ingest on change; process pending memory embeddings",
    )
    p_watchdog.add_argument(
        "--poll-interval",
        type=int,
        default=int(os.environ.get("WATCHDOG_POLL_INTERVAL", "600")),
        help="Seconds between .hbk checks (default: 600)",
    )
    p_watchdog.add_argument(
        "--pending-interval",
        type=int,
        default=int(os.environ.get("WATCHDOG_PENDING_INTERVAL", "600")),
        help="Seconds between pending memory processing (default: 600)",
    )
    p_watchdog.set_defaults(func=cmd_watchdog)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
