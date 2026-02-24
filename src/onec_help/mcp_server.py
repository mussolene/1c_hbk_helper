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


def _search_keyword(query: str, limit: int = 15) -> list[dict[str, Any]]:
    from .indexer import search_index_keyword
    return search_index_keyword(query, limit=limit)


def _list_titles(limit: int = 100, path_prefix: str = "") -> list[dict[str, Any]]:
    from .indexer import list_index_titles
    return list_index_titles(limit=limit, path_prefix=path_prefix or "")


def _index_status() -> dict[str, Any]:
    from .indexer import get_index_status
    return get_index_status()


def _get_topic(topic_path: str) -> str:
    from .indexer import get_topic_content
    base = _get_help_path()
    return get_topic_content(base, topic_path)


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
        """Search 1C help by natural language (semantic). Returns list of relevant topics with title, path, and snippet.
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
    def search_1c_help_keyword(query: str, limit: int = 15) -> str:
        """Search 1C help by exact substring in title and text (e.g. 'МенеджерКриптографии', 'интерактивный режим').
        Use when semantic search misses specific terms. limit: max results (default 15)."""
        results = _search_keyword(query.strip(), limit=limit)
        if not results:
            return "No keyword matches. Try search_1c_help for semantic search."
        lines = []
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. **{r.get('title', '')}** (path: {r.get('path', '')})")
            lines.append(f"   {r.get('text', '')[:300]}...")
        return "\n".join(lines)

    @mcp.tool()
    def get_1c_help_topic(topic_path: str) -> str:
        """Get full help topic content in Markdown by path. Path from search results (e.g. 'zif3_CryptoManager.md').
        Content is read from disk or from index if files were not persisted."""
        return _get_topic(topic_path) or "Topic not found."

    @mcp.tool()
    def list_1c_help_titles(limit: int = 100, path_prefix: str = "") -> str:
        """List topic titles and paths for browsing. path_prefix: filter by path start (e.g. 'zif' for command-line params)."""
        items = _list_titles(limit=limit, path_prefix=path_prefix)
        if not items:
            return "No topics in index or prefix filter too strict."
        lines = [f"{i}. **{r.get('title', '')}** — `{r.get('path', '')}`" for i, r in enumerate(items, 1)]
        return "\n".join(lines)

    @mcp.tool()
    def get_1c_help_index_status() -> str:
        """Check if 1C help is indexed: returns total topics count, collection name, and (if present) versions and languages.
        Use to verify that ingest completed successfully."""
        s = _index_status()
        err = s.get("error")
        if err:
            return f"Error: {err}"
        if not s.get("exists"):
            return "Index does not exist. Run ingest to index the help (e.g. docker compose exec mcp python -m onec_help ingest)."
        count = s.get("points_count")
        name = s.get("collection", "onec_help")
        lines = [f"Collection: **{name}**", f"Topics indexed: **{count}**"]
        if s.get("versions"):
            lines.append(f"Versions (sample): {', '.join(s['versions'])}")
        if s.get("languages"):
            lines.append(f"Languages (sample): {', '.join(s['languages'])}")
        return "\n".join(lines)

    @mcp.tool()
    def get_1c_function_info(name: str) -> str:
        """Get description, syntax, parameters, return value, and examples for a 1C function/method by name.
        name: function or method name (e.g. 'Формат', 'МенеджерКриптографии', 'ОбъединитьПериоды')."""
        # Prefer keyword search for exact names (e.g. МенеджерКриптографии)
        results = _search_keyword(name.strip(), limit=10)
        if not results:
            results = _search(name, limit=10)
        for r in results:
            path = r.get("path", "")
            if not path:
                continue
            if name.strip().lower() in (r.get("title") or "").lower():
                content = _get_topic(path)
                if content:
                    return content
        if results:
            content = _get_topic(results[0]["path"])
            if content:
                return content
        return "No topic found for this name. Try search_1c_help or search_1c_help_keyword first."

    if transport in ("sse", "http", "streamable-http"):
        path_val = (path or "/mcp").rstrip("/") or "/mcp"
        mcp.run(transport=transport, host=host, port=port, path=path_val)
    else:
        mcp.run(transport="stdio")
