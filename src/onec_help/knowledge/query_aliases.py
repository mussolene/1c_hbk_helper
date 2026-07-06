"""Data-driven prose-query aliases for common 1C API intents."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


def get_default_query_aliases_path() -> Path:
    return Path(__file__).with_name("query_api_aliases.json")


def _as_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def load_query_api_aliases(path: Path | None = None) -> list[dict[str, Any]]:
    target = (path or get_default_query_aliases_path()).expanduser().resolve()
    if not target.is_file():
        return []
    raw = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Query API aliases must be a JSON array")
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        alias_id = str(item.get("id") or "").strip()
        lookup = str(item.get("lookup") or "").strip()
        target_name = str(item.get("target") or "").strip()
        match_any = item.get("match_any")
        if not alias_id or lookup not in {"member", "object"} or not target_name:
            continue
        if not isinstance(match_any, list) or not match_any:
            continue
        out.append(
            {
                "id": alias_id,
                "lookup": lookup,
                "target": target_name,
                "match_any": [m for m in match_any if isinstance(m, dict)],
                "benchmark_queries": _as_list(item.get("benchmark_queries")),
            }
        )
    return out


@lru_cache(maxsize=1)
def _cached_query_api_aliases() -> tuple[dict[str, Any], ...]:
    return tuple(load_query_api_aliases())


def _normalize_query(value: str) -> tuple[str, str]:
    q_lower = " ".join((value or "").lower().split())
    compact = re.sub(r"[\s_\-]+", "", q_lower)
    return q_lower, compact


def _match_rule(rule: dict[str, Any], q_lower: str, compact: str) -> bool:
    all_terms = _as_list(rule.get("all"))
    if any(term.lower() not in q_lower for term in all_terms):
        return False

    any_terms = _as_list(rule.get("any"))
    if any_terms and not any(term.lower() in q_lower for term in any_terms):
        return False

    compact_any = _as_list(rule.get("compact_any"))
    if compact_any and not any(term.lower() in compact for term in compact_any):
        return False

    all_groups = rule.get("all_groups")
    if isinstance(all_groups, list):
        for group in all_groups:
            terms = _as_list(group)
            if terms and not any(term.lower() in q_lower for term in terms):
                return False
    return True


def resolve_query_api_aliases(question: str) -> list[dict[str, str]]:
    """Return data-driven API aliases matched by a natural-language query."""
    q_lower, compact = _normalize_query(question)
    if not q_lower:
        return []
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in _cached_query_api_aliases():
        if not any(_match_rule(rule, q_lower, compact) for rule in item.get("match_any") or []):
            continue
        key = (str(item["lookup"]), str(item["target"]))
        if key in seen:
            continue
        seen.add(key)
        out.append({"lookup": key[0], "target": key[1], "id": str(item.get("id") or "")})
    return out


def iter_query_alias_benchmark_cases() -> list[dict[str, Any]]:
    """Generate mesh-scorecard cases from packaged query aliases."""
    cases: list[dict[str, Any]] = []
    for item in _cached_query_api_aliases():
        target = str(item.get("target") or "").strip()
        lookup = str(item.get("lookup") or "").strip()
        if not target or not lookup:
            continue
        for idx, query in enumerate(item.get("benchmark_queries") or [], 1):
            cases.append(
                {
                    "id": f"query_alias_{item.get('id')}_{idx}",
                    "suite": "query_aliases",
                    "profile": "exact_api_surface",
                    "runner": "api_search",
                    "query": query,
                    "expected_lookup": lookup,
                    "expected_help_contains": [target],
                }
            )
    return cases
