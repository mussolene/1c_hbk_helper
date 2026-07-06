from onec_help.knowledge.answer_contract import build_answer_contract, contract_matches
from onec_help.knowledge.orchestrator.task_orchestrator import plan_1c_query


def test_build_answer_contract_routes_platform_fact() -> None:
    contract = build_answer_contract("HTTPСоединение.Получить")

    assert contract["route"] == "platform_fact"
    assert contract["action"] == "answer"
    assert contract["source_layers"] == ("platform",)
    assert contract["primary_tool"] == "get_1c_api_answer"


def test_build_answer_contract_routes_short_api_identifier() -> None:
    contract = build_answer_contract("ПрочитатьJSON")

    assert contract["route"] == "platform_fact"
    assert contract["source_layers"] == ("platform",)


def test_build_answer_contract_routes_form_document_metadata_phrase() -> None:
    contract = build_answer_contract("найди команду формы документа ЗаказПокупателя")

    assert contract["route"] == "metadata"
    assert "metadata" in contract["source_layers"]


def test_plan_1c_query_includes_answer_contract() -> None:
    plan = plan_1c_query("где вызывается процедура УстановитьСтатусДокумента")

    assert plan["answer_contract"]["route"] == "codebase_behavior"
    assert plan["answer_contract"]["primary_tool"] == "onec-context-toolkit:code"


def test_build_answer_contract_routes_code_behavior_from_symbol_context() -> None:
    contract = build_answer_contract(
        "объясни влияние этой процедуры",
        has_file_context=True,
        has_symbol_context=True,
    )

    assert contract["route"] == "codebase_behavior"
    assert "code" in contract["source_layers"]
    assert contract["answer_status"] == "code_inference_required"


def test_build_answer_contract_marks_generated_code_as_hypothesis() -> None:
    contract = build_answer_contract("напиши код чтения JSON")

    assert contract["route"] == "platform_example"
    assert "bsl_ls" in contract["source_layers"]
    assert contract["answer_status"] == "code_hypothesis_until_checked"


def test_contract_matches_checks_route_layers_tools_and_forbidden_layers() -> None:
    contract = build_answer_contract("проверь синтаксис измененного модуля")
    result = contract_matches(
        {
            "expected_answer_route": "validation_bsl_ls",
            "expected_action": "validate",
            "expected_answer_status": "requires_tool_run",
            "expected_layers_contains": ["bsl_ls"],
            "expected_tools_contains": ["Language Server"],
            "forbidden_layers": ["platform"],
        },
        contract,
    )

    assert all(result.values())
