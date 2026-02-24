# AGENTS.md — 1C Help MCP

## Назначение проекта

- Справка 1С: распаковка .hbk (7z), конвертация HTML → Markdown, индексация в Qdrant, MCP-сервер для поиска/чтения справки.
- Конфигурация через переменные окружения. БД — Qdrant в docker-compose.
- Дальнейшие этапы: один–два MCP по кодовой базе и метаданным 1С (задел в README).

## Команды и сценарии

- **Локально:** `python -m onec_help unpack/build-docs/build-index/serve/mcp <args>`
- **Docker:** `docker-compose up` (сервисы `qdrant` + `mcp`). В mcp смонтирован `/opt/1cv8`, cron раз в сутки в 3:00 запускает ingest.
- **Индекс вручную:** `docker compose exec mcp python -m onec_help ingest` (каталог версий — `HELP_SOURCE_BASE`, подпапки = версии 1С, поиск .hbk рекурсивно, в т.ч. в `bin/` на Windows).

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
