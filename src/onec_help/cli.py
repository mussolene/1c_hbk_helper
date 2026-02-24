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
