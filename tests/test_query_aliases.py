import json
from pathlib import Path

import pytest

from onec_help.knowledge.query_aliases import (
    iter_query_alias_benchmark_cases,
    load_query_api_aliases,
    resolve_query_api_aliases,
)


def test_load_query_api_aliases_filters_invalid_rows(tmp_path: Path) -> None:
    path = tmp_path / "aliases.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "ok",
                    "lookup": "member",
                    "target": "Тест.Метод",
                    "match_any": [{"all": ["тест"]}],
                    "benchmark_queries": ["тестовый запрос"],
                },
                {"id": "bad_lookup", "lookup": "bad", "target": "X", "match_any": [{}]},
                {"id": "bad_match", "lookup": "member", "target": "X", "match_any": []},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rows = load_query_api_aliases(path)

    assert len(rows) == 1
    assert rows[0]["id"] == "ok"
    assert rows[0]["benchmark_queries"] == ["тестовый запрос"]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Как в 1С прочитать JSON в Соответствие?", "ПрочитатьJSON"),
        ("Как проверить что значение заполнено и не пустое?", "ЗначениеЗаполнено"),
        ("Как найти значение в массиве и получить индекс элемента?", "Массив.Найти"),
        ("Как создать новый уникальный идентификатор?", "УникальныйИдентификатор.По умолчанию"),
    ],
)
def test_resolve_query_api_aliases_from_packaged_data(query: str, expected: str) -> None:
    targets = [item["target"] for item in resolve_query_api_aliases(query)]

    assert expected in targets


def test_iter_query_alias_benchmark_cases_uses_packaged_aliases() -> None:
    cases = iter_query_alias_benchmark_cases()

    assert any(case["runner"] == "api_search" for case in cases)
    assert any("ПрочитатьJSON" in case["expected_help_contains"] for case in cases)
