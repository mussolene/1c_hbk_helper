"""CLI: unpack, build-docs, serve, build-index, mcp."""

import argparse
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
    from .web import app
    port = int(_env_path("PORT", "5000") or "5000")
    app.config["BASE_DIR"] = args.directory
    app.run(host="0.0.0.0", port=port, debug=args.debug)
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
        )
        print(f"Indexed {count} chunks")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_index_status(args: argparse.Namespace) -> int:
    """Print index status: points count, versions, languages."""
    from .indexer import get_index_status
    host = os.environ.get("QDRANT_HOST", "localhost")
    port = int(os.environ.get("QDRANT_PORT", "6333"))
    collection = os.environ.get("QDRANT_COLLECTION", "onec_help")
    s = get_index_status(qdrant_host=host, qdrant_port=port, collection=collection)
    if s.get("error"):
        print(f"Error: {s['error']}", file=sys.stderr)
        return 1
    if not s.get("exists"):
        print("Index does not exist. Run: python -m onec_help ingest")
        return 0
    print(f"Collection: {s.get('collection', 'onec_help')}")
    print(f"Topics indexed: {s.get('points_count', 0)}")
    if s.get("versions"):
        print(f"Versions (sample): {', '.join(s['versions'])}")
    if s.get("languages"):
        print(f"Languages (sample): {', '.join(s['languages'])}")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    """Ingest .hbk from multiple read-only source dirs: unpack to temp, build docs, index, cleanup."""
    from pathlib import Path
    from .ingest import run_ingest, discover_version_dirs, parse_source_dirs_env, parse_languages_env
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
        print("Error: no source directories. Set HELP_SOURCE_BASE (path to folder with version subdirs) or use --sources / --sources-file", file=sys.stderr)
        return 1
    raw_lang = getattr(args, "languages", None)
    if raw_lang is not None:
        languages = parse_languages_env(raw_lang if raw_lang.strip() else "all")
    else:
        languages = parse_languages_env(os.environ.get("HELP_LANGUAGES"))
    try:
        n = run_ingest(
            source_dirs_with_versions=sources,
            languages=languages,
            temp_base=args.temp_base or os.environ.get("HELP_INGEST_TEMP", "/tmp/help_ingest"),
            qdrant_host=os.environ.get("QDRANT_HOST", "localhost"),
            qdrant_port=int(os.environ.get("QDRANT_PORT", "6333")),
            collection=os.environ.get("QDRANT_COLLECTION", "onec_help"),
            incremental=True,
            max_workers=getattr(args, "workers", 4),
            max_tasks=getattr(args, "max_tasks", None),
            verbose=not getattr(args, "quiet", False),
            dry_run=getattr(args, "dry_run", False),
            index_batch_size=getattr(args, "index_batch_size", 500),
        )
        print(f"Ingested and indexed {n} chunks")
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
    run_mcp(
        help_path=Path(args.directory),
        transport=transport,
        host=host,
        port=port,
        path=path,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="onec_help", description="1C Help: unpack, docs, index, MCP")
    sub = parser.add_subparsers(dest="command", required=True)

    # unpack
    p_unpack = sub.add_parser("unpack", help="Unpack .hbk with 7z")
    p_unpack.add_argument("archive", type=str, help="Path to .hbk file")
    p_unpack.add_argument("--output-dir", "-o", type=str, default="./unpacked", help="Output directory")
    p_unpack.set_defaults(func=cmd_unpack)

    # build-docs
    p_docs = sub.add_parser("build-docs", help="Generate Markdown from HTML")
    p_docs.add_argument("project_dir", type=str, help="Directory with HTML files")
    p_docs.add_argument("--output", "-o", type=str, help="Output directory (default: project_dir/docs_md)")
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
    p_idx.add_argument("--incremental", action="store_true", help="Add/update only, do not recreate collection (new files in folder will be indexed)")
    p_idx.set_defaults(func=cmd_build_index)

    # index-status
    p_status = sub.add_parser("index-status", help="Show 1C help index status (topic count, versions, languages)")
    p_status.set_defaults(func=cmd_index_status)

    # ingest
    p_ingest = sub.add_parser("ingest", help="Ingest .hbk from multiple read-only dirs (temp unpack, index, cleanup)")
    p_ingest.add_argument("--sources", "-s", type=str, nargs="*", help="Alternating path:version (or set HELP_SOURCE_BASE to scan a folder of version subdirs)")
    p_ingest.add_argument("--sources-file", type=str, help="File with lines: path or path:version")
    p_ingest.add_argument("--languages", "-l", type=str, default=None, help="Comma-separated, e.g. ru or ru,en; default from HELP_LANGUAGES; empty=all")
    p_ingest.add_argument("--temp-base", type=str, default=None, help="Temp dir in container (default HELP_INGEST_TEMP or /tmp/help_ingest)")
    p_ingest.add_argument("--workers", "-w", type=int, default=4, help="Parallel workers for unpack/build (default 4)")
    p_ingest.add_argument("--max-tasks", "-n", type=int, default=None, help="Process only first N .hbk files (avoids timeout; run multiple times for full index)")
    p_ingest.add_argument("--quiet", "-q", action="store_true", help="No progress output (default: print progress to stderr)")
    p_ingest.add_argument("--dry-run", action="store_true", help="Only report how many .hbk tasks would be processed (no unpack/index)")
    p_ingest.add_argument("--index-batch-size", type=int, default=500, metavar="N", help="Index N files per upsert (default 500); smaller = more progress output, less memory")
    p_ingest.set_defaults(func=cmd_ingest)

    # mcp
    p_mcp = sub.add_parser("mcp", help="Run MCP server (stdio, sse, http, streamable-http)")
    p_mcp.add_argument("directory", type=str, help="Directory with help (.md or HTML)")
    p_mcp.add_argument("--transport", "-t", type=str, default=None, help="Transport: stdio (default), sse, http, streamable-http")
    p_mcp.add_argument("--host", type=str, default=None, help="Host for sse/http (default: 127.0.0.1). Use 0.0.0.0 in Docker.")
    p_mcp.add_argument("--port", "-p", type=int, default=None, help="Port for sse/http (default: 5050)")
    p_mcp.add_argument("--path", type=str, default=None, help="URL path (default: /mcp)")
    p_mcp.set_defaults(func=cmd_mcp)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
