# AGENTS.md — 1C Help MCP

## Назначение проекта

- Справка 1С: распаковка .hbk (только 7z), конвертация HTML → Markdown, индексация в Qdrant, веб-просмотр и MCP-сервер для поиска/чтения справки.
- Конфигурация только через переменные окружения. БД — отдельный контейнер Qdrant в docker-compose.
- Дальнейшие этапы: один–два MCP по кодовой базе и метаданным 1С (в плане только задел в README и структуре).

## Команды и сценарии

- **Локально:** `python -m onec_help unpack/build-docs/build-index/serve/mcp <args>`
- **Docker:** `docker-compose up` (сервисы `app` + `qdrant`); приложение по умолчанию — `serve /data`.
- **Индекс:** после монтирования справки в `/data`: `build-docs /data -o /data/docs_md`, затем `build-index /data/docs_md` (нужны `QDRANT_HOST`, `QDRANT_PORT`).

## Структура кода

- `src/onec_help/`: пакет (unpack, categories, html2md, tree, web, indexer, mcp_server, cli).
- `unpack` — 7z; `categories` — парсинг `__categories__` и дерево TOC; `html2md` — HTML → Markdown; `tree` — дерево для веба; `web` — Flask; `indexer` — Qdrant; `mcp_server` — FastMCP, инструменты search_1c_help, get_1c_help_topic, get_1c_function_info.
- Тесты в `tests/`, покрытие ≥90% (pytest-cov, `--cov-fail-under=90`).
- Фикстуры — минимальный срез справки в `tests/fixtures/help_sample/`.

## MCP и конфиг Cursor

- MCP работает **в контейнере** по протоколу **streamable-http** (порт 5050). Рабочий конфиг: **`.cursor/mcp.json`** с полем `url: "http://localhost:5050/mcp"` (без command/stdio). Пример — `docs/mcp.json.example`.
- **При добавлении новых MCP-сервисов** их нужно прописать в `.cursor/mcp.json`: для удалённого сервера — запись в `mcpServers` с полем `url`; для локального — `command`, `args`, при необходимости `env`. После изменений конфига Cursor перезапускают.

## Правила

- Язык кода и комментариев — по контексту (рус/англ). Пути и конфигурация — только через аргументы и env, без хардкода.
- Не трогать план в `.cursor/plans/`. При доработках сохранять совместимость с docker-compose и Qdrant.
- Использовать subagent’ы при необходимости для объёмных задач.
