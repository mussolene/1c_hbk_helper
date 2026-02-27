# AGENTS.md — 1C Help MCP

## Назначение проекта

- Справка 1С: распаковка .hbk (7z), конвертация HTML → Markdown, индексация в Qdrant, MCP-сервер для поиска/чтения справки.
- Конфигурация через переменные окружения. БД — Qdrant в docker-compose.
- Дальнейшие этапы: один–два MCP по кодовой базе и метаданным 1С (задел в README).

## Команды и сценарии

- **Локально:** `python -m onec_help unpack/build-docs/build-index/ingest/load-snippets/load-standards/parse-fastcode/watchdog/serve/mcp <args>`
- **Docker:** `docker-compose up` (сервисы `qdrant` + `mcp` + `bsl-bridge`). В mcp смонтирован `/opt/1cv8`, cron раз в сутки в 3:00 запускает ingest; при `WATCHDOG_ENABLED=1` — watchdog в фоне. bsl-bridge — BSL LS для проекта (volume `.:/projects`, код в `src` или в корне).
- **Split mode:** `docker compose -f docker-compose.split.yml up -d` — mcp только API (MCP_MODE=api), ingest-worker — batch (ingest, cron, load-snippets, watchdog). Индексация вручную: `exec ingest-worker python -m onec_help ingest`.
- **Индекс вручную:** `docker compose exec mcp python -m onec_help ingest` (single) или `docker compose -f docker-compose.split.yml exec ingest-worker python -m onec_help ingest` (split). (каталог версий — `HELP_SOURCE_BASE`, подпапки = версии 1С, поиск .hbk рекурсивно, в т.ч. в `bin/` на Windows).
- **Сниппеты:** `docs/snippets/` — примеры (не загружаются). Реальные — из тома `./snippets:/data/snippets`, при старте `load-snippets`. `load-snippets --from-project src` — из проекта 1С. `make parse-fastcode`, `make load-snippets`, `make snippets`.
- **Стандарты:** `make load-standards` — по умолчанию STANDARDS_REPO (авто-скачивание, temp удаляется); либо STANDARDS_DIR (volume) или путь в ARGS.

## Структура кода

- `src/onec_help/`: пакет (unpack, categories, html2md, tree, web, indexer, memory, parse_fastcode, standards_loader, watchdog, mcp_server, cli).
- `unpack` — 7z; `categories` — парсинг `__categories__` и дерево TOC; `html2md` — HTML → Markdown; `tree` — дерево для веба; `web` — Flask; `indexer` — Qdrant; `memory` — тройная память (short/medium/long); `watchdog` — мониторинг .hbk и pending embeddings; `mcp_server` — FastMCP, инструменты search_1c_help, search_1c_help_with_content, get_1c_code_answer, get_1c_help_topic, get_1c_function_info, save_1c_snippet, get_form_metadata, get_module_info, get_1c_help_related, compare_1c_help, trigger_reindex.
- Тесты в `tests/`, покрытие ≥90% (pytest-cov, `--cov-fail-under=90`).
- Фикстуры — минимальный срез справки в `tests/fixtures/help_sample/`.

## MCP и конфиг Cursor

- MCP работает **в контейнере** по протоколу **streamable-http** (порт 5050). Рабочий конфиг: **`.cursor/mcp.json`** с полем `url: "http://localhost:5050/mcp"` (без command/stdio). Пример — `docs/mcp.json.example`.
- **Skill и Rules:** примеры для индексации и синхронизации — `docs/cursor-examples/`. Папка `.cursor/` исключена из git; при настройке Cursor скопируйте содержимое `docs/cursor-examples/` в `.cursor/skills/` и `.cursor/rules/`. При доработке MCP или workflow — обновляйте `docs/cursor-examples/` как зависимость.
- **Рекомендуемый порядок вызовов:**
  1. Ответ с кодом — `get_1c_code_answer` (при необходимости `code_only=True`).
  2. Недостаток деталей — `get_1c_help_topic(topic_path)` (параметр `topic_path`, не `path`).
  3. Точные имена API — `search_1c_help_keyword` с полным именем (в т.ч. `Тип.Метод`).
  4. Несколько совпадений в `get_1c_function_info` — указывать `choose_index`.
  5. После генерации кода — `save_1c_snippet` для сохранения полезных примеров.
- **Типовые ловушки:** ПрочитатьJSON возвращает Структуру по умолчанию — для Соответствия указывать `ПрочитатьВСоответствие=Истина`. HTTPСоединение.Получить — только на сервере. Имена методов вида `Тип.Метод` передавать целиком в `search_1c_help_keyword`.
- **При добавлении новых MCP-сервисов** их нужно прописать в `.cursor/mcp.json`: для удалённого сервера — запись в `mcpServers` с полем `url`; для локального — `command`, `args`, при необходимости `env`. После изменений конфига Cursor перезапускают.

## Безопасность

- Веб (serve) и MCP по HTTP не имеют аутентификации; рассчитаны **только** на доверенную сеть (localhost/VPN). При экспозиции в интернет — обязателен обратный прокси с аутентификацией.
- **HELP_SERVE_ALLOWED_DIRS** обязательна для serve: при пустом значении форма не принимает любой путь (защита от чтения произвольных каталогов). Задайте список разрешённых базовых каталогов через запятую.

## Конфиденциальность и NDA

- **Embedding API:** текст справки 1С и поисковые запросы отправляются на внешний сервис (LM Studio, OpenAI и т.п.). При работе с конфиденциальными данными или NDA используйте on-prem сервис эмбеддингов (EMBEDDING_API_URL на внутренний хост).
- **Memory (MEMORY_ENABLED=1):** история сессий (topic_path, save_snippet, exchange) хранится в JSONL и Qdrant. Учитывайте политику хранения и доступ к этим данным.
- **save_1c_snippet:** сохранённый код пишется в memory. При SAVE_SNIPPET_TO_FILES=1 — также в SNIPPETS_DIR. При конфиденциальном коде настройте SNIPPETS_DIR и MEMORY_BASE_PATH в защищённое место.
- **Логи:** в production (PRODUCTION=1) в ответах API и логах не раскрываются полные пути и текст исключений.

## Правила

- Язык кода и комментариев — по контексту (рус/англ). Пути и конфигурация — только через аргументы и env, без хардкода.
- **Сохранять рабочий код 1С:** при выдаче исполняемого примера 1С, которого нет в базовых сниппетах, вызывать `save_1c_snippet` с кодом и описанием — это улучшит `get_1c_code_answer` в следующих сессиях.
- Не трогать план в `.cursor/plans/`. При доработках сохранять совместимость с docker-compose и Qdrant. При изменении MCP или workflow — проверить и обновить `docs/cursor-examples/` (skill, rules).
- Использовать subagent'ы при необходимости для объёмных задач.

### Работа с 1С-кодом

- **Два MCP:** при генерации кода — 1c-help (`get_1c_code_answer`, `search_1c_help_keyword`); при проверке/рефакторинге — lsp-bsl-bridge (`document_diagnostics`, `code_actions`). Если 1c-help недоступен (нет индекса) — опереться на BSL LS и memory.
- **После правок 1С:** вызывать `document_diagnostics` для проверки ошибок, предупреждений и соответствия стандартам BSL LS. URI для Docker: `file:///projects/<path>/Module.bsl` (volume `.:/projects`).
- **Стандарты:** учитывать правила 1С (BSL LS diagnostics + v8-code-style из `load-standards`).

## Workflow разработки 1С с BSL LS

1. **Индексация.** `make up` или `docker compose up -d` — bsl-bridge входит в compose, volume `.:/projects`. Дождаться индексации (`lsp_status`).
2. **Ориентирование.** `project_analysis` — поиск символов/файлов; `symbol_explore` — детали по символу; `call_graph` — граф вызовов перед рефакторингом.
3. **Написание кода.** `get_1c_code_answer` — примеры и API; `project_analysis` — где добавить код; `symbol_explore` — сигнатуры и паттерны; `save_1c_snippet` — сохранить новый фрагмент.
4. **Рефакторинг.** `call_graph` → `document_diagnostics` → `code_actions` → `prepare_rename`/`rename`; после массовых правок — `did_change_watched_files`.
5. **Проверка.** `document_diagnostics` — финальная проверка.

**Рефакторинг существующего кода:** `document_diagnostics(uri)` → приоритизация (ERROR > WARNING > INFO) → правки → повтор diagnostics. Один файл за раз; после batch — вызвать `did_change_watched_files`.
