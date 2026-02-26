# AGENTS.md — 1C Help MCP

## Назначение проекта

- Справка 1С: распаковка .hbk (7z), конвертация HTML → Markdown, индексация в Qdrant, MCP-сервер для поиска/чтения справки.
- Конфигурация через переменные окружения. БД — Qdrant в docker-compose.
- Дальнейшие этапы: один–два MCP по кодовой базе и метаданным 1С (задел в README).

## Команды и сценарии

- **Локально:** `python -m onec_help unpack/build-docs/build-index/ingest/load-snippets/load-standards/parse-fastcode/watchdog/serve/mcp <args>`
- **Docker:** `docker-compose up` (сервисы `qdrant` + `mcp`). В mcp смонтирован `/opt/1cv8`, cron раз в сутки в 3:00 запускает ingest; при `WATCHDOG_ENABLED=1` — watchdog в фоне (мониторинг .hbk, pending memory).
- **Индекс вручную:** `docker compose exec mcp python -m onec_help ingest` (каталог версий — `HELP_SOURCE_BASE`, подпапки = версии 1С, поиск .hbk рекурсивно, в т.ч. в `bin/` на Windows).
- **Сниппеты:** `docs/snippets/` — примеры (не загружаются). Реальные — из тома `./snippets:/data/snippets`, при старте `load-snippets`. `make parse-fastcode`, `make load-snippets`, `make snippets`.
- **Стандарты:** `make load-standards` — по умолчанию STANDARDS_REPO (авто-скачивание, temp удаляется); либо STANDARDS_DIR (volume) или путь в ARGS.

## Структура кода

- `src/onec_help/`: пакет (unpack, categories, html2md, tree, web, indexer, memory, parse_fastcode, standards_loader, watchdog, mcp_server, cli).
- `unpack` — 7z; `categories` — парсинг `__categories__` и дерево TOC; `html2md` — HTML → Markdown; `tree` — дерево для веба; `web` — Flask; `indexer` — Qdrant; `memory` — тройная память (short/medium/long); `watchdog` — мониторинг .hbk и pending embeddings; `mcp_server` — FastMCP, инструменты search_1c_help, search_1c_help_with_content, get_1c_code_answer, get_1c_help_topic, get_1c_function_info, save_1c_snippet, get_1c_help_related, compare_1c_help, trigger_reindex.
- Тесты в `tests/`, покрытие ≥90% (pytest-cov, `--cov-fail-under=90`).
- Фикстуры — минимальный срез справки в `tests/fixtures/help_sample/`.

## MCP и конфиг Cursor

- MCP работает **в контейнере** по протоколу **streamable-http** (порт 5050). Рабочий конфиг: **`.cursor/mcp.json`** с полем `url: "http://localhost:5050/mcp"` (без command/stdio). Пример — `docs/mcp.json.example`.
- **Рекомендуемый порядок вызовов:** для быстрого ответа с кодом — `get_1c_code_answer`; при недостатке деталей — `get_1c_help_topic(path)`; для точных имён API — `search_1c_help_keyword`.
- **При добавлении новых MCP-сервисов** их нужно прописать в `.cursor/mcp.json`: для удалённого сервера — запись в `mcpServers` с полем `url`; для локального — `command`, `args`, при необходимости `env`. После изменений конфига Cursor перезапускают.

## Безопасность

- Веб (serve) и MCP по HTTP не имеют аутентификации; рассчитаны на доверенную сеть (localhost/VPN). Не выставлять наружу без обратного прокси с аутентификацией.

## Правила

- Язык кода и комментариев — по контексту (рус/англ). Пути и конфигурация — только через аргументы и env, без хардкода.
- **Сохранять рабочий код 1С:** при выдаче исполняемого примера 1С, которого нет в базовых сниппетах, вызывать `save_1c_snippet` с кодом и описанием — это улучшит `get_1c_code_answer` в следующих сессиях.
- Не трогать план в `.cursor/plans/`. При доработках сохранять совместимость с docker-compose и Qdrant.
- Использовать subagent'ы при необходимости для объёмных задач.

### Работа с 1С-кодом

- **Два MCP:** при генерации/редактировании кода 1С использовать **оба** MCP: `1c-help` (справка, сниппеты, память) и `lsp-bsl-bridge` (BSL LS — навигация, диагностика, рефакторинг).
- **После правок 1С:** вызывать `document_diagnostics` для проверки ошибок, предупреждений и соответствия стандартам BSL LS.
- **Стандарты:** учитывать правила 1С (BSL LS diagnostics + v8-code-style из `load-standards`).

## Workflow разработки 1С с BSL LS

1. **Индексация.** Запустить mcp-bsl-lsp-bridge с volume на каталог проекта → дождаться индексации (`lsp_status`).
2. **Ориентирование.** `project_analysis` — поиск символов/файлов; `symbol_explore` — детали по символу; `call_graph` — граф вызовов перед рефакторингом.
3. **Написание кода.** `get_1c_code_answer` — примеры и API; `project_analysis` — где добавить код; `symbol_explore` — сигнатуры и паттерны; `save_1c_snippet` — сохранить новый фрагмент.
4. **Рефакторинг.** `call_graph` → `document_diagnostics` → `code_actions` → `prepare_rename`/`rename`; после массовых правок — `did_change_watched_files`.
5. **Проверка.** `document_diagnostics` — финальная проверка.
