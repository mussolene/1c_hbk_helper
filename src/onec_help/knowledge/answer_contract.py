"""Answer routing contract for 1C developer questions.

This module is intentionally small and dependency-light: it classifies the
question into the source layer and next tool that should own the answer. The
retrieval code can then stay focused on facts, while scorecards can test the
product contract directly.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AnswerContract:
    route: str
    action: str
    source_layers: tuple[str, ...]
    primary_tool: str
    next_tools: tuple[str, ...]
    answer_status: str
    confidence: float
    confirmed_by: tuple[str, ...]
    assumptions: tuple[str, ...] = ()
    missing_context: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _norm(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _looks_like_exact_api(value: str) -> bool:
    clean = (value or "").strip()
    return bool(clean) and "." in clean and " " not in clean


def _looks_like_api_identifier(value: str) -> bool:
    clean = (value or "").strip()
    if not clean or " " in clean or len(clean) < 3:
        return False
    if "." in clean:
        return True
    first = clean[0]
    return first.isupper() or ("А" <= first <= "Я")


def _toolkit_hint(route: str) -> tuple[str, ...]:
    if route == "metadata":
        return (
            "search_1c_metadata_exact",
            "get_1c_metadata_object",
            "onec-context-toolkit:metadata",
        )
    if route == "codebase_behavior":
        return ("onec-context-toolkit:code", "get_1c_task_context")
    if route == "full_source_verification":
        return ("onec-context-toolkit:full",)
    if route == "validation_bsl_ls":
        return ("BSL Language Server analyze/format",)
    if route == "standards_or_snippets":
        return ("search_1c_standards", "search_1c_snippets")
    if route == "platform_example":
        return ("search_1c_api", "BSL Language Server analyze")
    if route == "platform_fact":
        return ("get_1c_api_answer", "search_1c_api")
    return ("get_1c_quick_guide",)


def build_answer_contract(
    query: str,
    *,
    route_kind: str | None = None,
    has_file_context: bool = False,
    has_symbol_context: bool = False,
    config_version: str | None = None,
) -> dict[str, Any]:
    q = _norm(query)
    exact_api = _looks_like_exact_api(query)

    validation_markers = (
        "bsl ls",
        "language server",
        "статический анализ",
        "диагностик",
        "проверить код",
        "проверка кода",
        "отформат",
        "синтакс",
        "ошибка компиля",
    )
    full_markers = (
        "xml",
        "raw",
        "исходн",
        "точное представление",
        "файл формы",
        "подтвердить exact",
    )
    code_markers = (
        "где вызывается",
        "кто вызывает",
        "callers",
        "callees",
        "обработчик",
        "процедура",
        "функция",
        "почему документ",
        "влияет на",
        "поведение",
    )
    metadata_markers = (
        "метаданн",
        "реквизит",
        "табличн",
        "тип реквизита",
        "форма",
        "форм",
        "команда",
        "документа",
        "document.",
        "catalog.",
        "accumulationregister.",
        "справочник.",
        "документ.",
        "регистр",
    )
    standards_markers = ("стандарт", "v8std", "соглашени", "стиль", "сниппет", "snippet")
    code_request_markers = (
        "пример",
        "код",
        "написать",
        "реализовать",
        "готов",
        "как сделать",
        "как использовать",
    )

    route = "ambiguous"
    action = "clarify"
    source_layers: tuple[str, ...] = ()
    primary_tool = "get_1c_quick_guide"
    answer_status = "needs_route"
    confidence = 0.35
    confirmed_by: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    missing_context: tuple[str, ...] = ()

    if _has_any(q, validation_markers):
        route = "validation_bsl_ls"
        action = "validate"
        source_layers = ("bsl_ls",)
        primary_tool = "BSL Language Server analyze/format"
        answer_status = "requires_tool_run"
        confirmed_by = ("BSL Language Server diagnostics",)
        confidence = 0.85
        if not has_file_context:
            missing_context = ("changed file or source path",)
    elif _has_any(q, full_markers):
        route = "full_source_verification"
        action = "delegate_to_tool"
        source_layers = ("full",)
        primary_tool = "onec-context-toolkit:full"
        answer_status = "needs_source_verification"
        confirmed_by = ("raw ConfigDump/source pack",)
        confidence = 0.8
    elif _has_any(q, code_markers) or (has_file_context and has_symbol_context):
        route = "codebase_behavior"
        action = "delegate_to_tool"
        source_layers = ("code",)
        primary_tool = "onec-context-toolkit:code"
        answer_status = "code_inference_required"
        confirmed_by = ("code pack callers/callees",)
        confidence = 0.82
    elif _has_any(q, metadata_markers) or route_kind in {
        "metadata_exact",
        "metadata_surface_chain",
    }:
        route = "metadata"
        action = "retrieve"
        source_layers = ("metadata",)
        primary_tool = "search_1c_metadata_exact"
        answer_status = "source_fact"
        confirmed_by = ("metadata graph or toolkit metadata pack",)
        confidence = 0.82
        if not config_version:
            assumptions = ("single metadata target/version or auto-selected config_version",)
    elif _has_any(q, standards_markers) or route_kind == "standards_or_snippets":
        route = "standards_or_snippets"
        action = "retrieve"
        source_layers = ("standards", "snippets")
        primary_tool = "search_1c_standards"
        answer_status = "source_candidate"
        confirmed_by = ("standards/snippet memory",)
        confidence = 0.78
    elif _has_any(q, code_request_markers):
        route = "platform_example"
        action = "answer_then_validate"
        source_layers = ("platform", "bsl_ls")
        primary_tool = "search_1c_api"
        answer_status = "code_hypothesis_until_checked"
        confirmed_by = ("structured platform help",)
        assumptions = ("generated/adapted code must be checked by BSL LS",)
        confidence = 0.72
    elif (
        exact_api
        or _looks_like_api_identifier(query)
        or route_kind in {"platform_api_exact", "platform_surface_chain", "conceptual_help"}
    ):
        route = "platform_fact"
        action = "answer"
        source_layers = ("platform",)
        primary_tool = "get_1c_api_answer" if exact_api else "answer_1c_help_question"
        answer_status = "source_fact"
        confirmed_by = ("structured platform help",)
        confidence = 0.8
    else:
        route = "ambiguous"
        action = "clarify_or_search"
        source_layers = ("platform", "metadata", "code")
        primary_tool = "get_1c_task_context"
        answer_status = "needs_route"
        confirmed_by = ()
        missing_context = (
            "whether the question is about platform API, configuration metadata, or code behavior",
        )

    contract = AnswerContract(
        route=route,
        action=action,
        source_layers=source_layers,
        primary_tool=primary_tool,
        next_tools=_toolkit_hint(route),
        answer_status=answer_status,
        confidence=confidence,
        confirmed_by=confirmed_by,
        assumptions=assumptions,
        missing_context=missing_context,
    )
    return contract.as_dict()


def contract_matches(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, bool]:
    layers = {str(x) for x in contract.get("source_layers") or ()}
    tools_blob = " ".join(
        [
            str(contract.get("primary_tool") or ""),
            *[str(x) for x in contract.get("next_tools") or ()],
        ]
    ).lower()
    route_ok = not case.get("expected_answer_route") or str(contract.get("route") or "") == str(
        case.get("expected_answer_route") or ""
    )
    action_ok = not case.get("expected_action") or str(contract.get("action") or "") == str(
        case.get("expected_action") or ""
    )
    status_ok = not case.get("expected_answer_status") or str(
        contract.get("answer_status") or ""
    ) == str(case.get("expected_answer_status") or "")
    layers_ok = all(str(x) in layers for x in case.get("expected_layers_contains") or ())
    tools_ok = all(str(x).lower() in tools_blob for x in case.get("expected_tools_contains") or ())
    forbidden_layers_ok = not any(str(x) in layers for x in case.get("forbidden_layers") or ())
    return {
        "answer_route_ok": route_ok,
        "answer_action_ok": action_ok,
        "answer_status_ok": status_ok,
        "answer_layers_ok": layers_ok,
        "answer_tools_ok": tools_ok,
        "answer_forbidden_layers_ok": forbidden_layers_ok,
    }
