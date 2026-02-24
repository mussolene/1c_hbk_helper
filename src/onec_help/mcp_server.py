"""MCP server for 1C Help: search_1c_help, get_1c_help_topic, get_1c_function_info."""

from pathlib import Path
from typing import Any

# Prefer fastmcp; fallback to mcp package
try:
    from fastmcp import FastMCP
    _HAS_FASTMCP = True
except ImportError:
    FastMCP = None  # type: ignore
    _HAS_FASTMCP = False

_HELP_PATH = None  # Path | None


def _get_help_path() -> Path:
    if _HELP_PATH is None:
        import os
        p = os.environ.get("HELP_PATH")
        if not p:
            raise RuntimeError("HELP_PATH not set")
        return Path(p)
    return _HELP_PATH


def _search(query: str, limit: int = 10) -> list[dict[str, Any]]:
    from .indexer import search_index
    return search_index(query, limit=limit)


def _get_topic(topic_path: str) -> str:
    from .indexer import get_topic_by_path
    base = _get_help_path()
    return get_topic_by_path(base, topic_path)


def run_mcp(
    help_path: Path,
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 5050,
    path: str = "/mcp",
) -> None:
    """Run MCP server. help_path: directory with .md or HTML.
    transport: stdio | sse | http | streamable-http. For http/sse, host/port/path used."""
    global _HELP_PATH
    _HELP_PATH = help_path.resolve()

    if not _HAS_FASTMCP:
        raise RuntimeError("fastmcp required: pip install fastmcp")

    mcp = FastMCP("1C Help")

    @mcp.tool()
    def search_1c_help(query: str, limit: int = 10) -> str:
        """Search 1C help by natural language. Returns list of relevant topics with title, path, and snippet.
        query: search text (e.g. 'Формат', 'Запрос.ПакетПолучения', 'синтаксис ОбъединитьПериоды').
        limit: max number of results (default 10)."""
        results = _search(query, limit=limit)
        if not results:
            return "No results found. Ensure build-index was run and Qdrant is available."
        lines = []
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. **{r.get('title', '')}** (path: {r.get('path', '')})")
            lines.append(f"   {r.get('text', '')[:300]}...")
        return "\n".join(lines)

    @mcp.tool()
    def get_1c_help_topic(topic_path: str) -> str:
        """Get full help topic content in Markdown by path. Path is relative to help root (e.g. 'objects/catalog63/table75/fields/field626.md' or '.html')."""
        return _get_topic(topic_path) or "Topic not found."

    @mcp.tool()
    def get_1c_function_info(name: str) -> str:
        """Get description, syntax, parameters, return value, and examples for a 1C function/method by name.
        name: function or method name (e.g. 'Формат', 'ОбъединитьПериоды')."""
        results = _search(name, limit=5)
        for r in results:
            if name.lower() in (r.get("title") or "").lower():
                path = r.get("path", "")
                if path:
                    content = _get_topic(path)
                    if content:
                        return content
        if results:
            return _get_topic(results[0]["path"]) or "Not found."
        return "No topic found for this name. Try search_1c_help first."

    if transport in ("sse", "http", "streamable-http"):
        path_val = (path or "/mcp").rstrip("/") or "/mcp"
        mcp.run(transport=transport, host=host, port=port, path=path_val)
    else:
        mcp.run(transport="stdio")
