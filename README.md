# 1C Help — MCP в Docker

[![Test](https://github.com/mussolene/1c_hbk_helper/actions/workflows/test.yml/badge.svg)](https://github.com/mussolene/1c_hbk_helper/actions/workflows/test.yml)
[![Lint](https://github.com/mussolene/1c_hbk_helper/actions/workflows/lint.yml/badge.svg)](https://github.com/mussolene/1c_hbk_helper/actions/workflows/lint.yml)
[![Coverage](https://codecov.io/gh/mussolene/1c_hbk_helper/graph/badge.svg)](https://codecov.io/gh/mussolene/1c_hbk_helper)
[![Release](https://github.com/mussolene/1c_hbk_helper/actions/workflows/release.yml/badge.svg)](https://github.com/mussolene/1c_hbk_helper/releases)


Справка 1С: распаковка .hbk (7z), конвертация в Markdown, индексация в Qdrant, MCP-сервер для поиска и чтения справки.

## Требования

- Python 3.9+ (для MCP с fastmcp — 3.10+)
- Docker и docker-compose (для контейнерного запуска)
- 7z (p7zip-full) — для распаковки .hbk внутри контейнера

## Установка (локально)

```bash
pip install -e .
# С поддержкой MCP (Python 3.10+):
pip install -e ".[mcp]"
# Для тестов и линтера:
pip install -e ".[dev]"
```

## Команды CLI

| Команда | Описание |
|--------|----------|
| **`unpack <archive> [--output-dir]`** | Распаковать один .hbk через 7z |
| **`unpack-dir [source_dir] [-o output]`** | Распаковать все .hbk из дерева каталогов в указанную директорию (без индексации). Источники: `source_dir`, `HELP_SOURCE_BASE` или `--sources` |
| **`build-docs <project_dir> [--output]`** | Сгенерировать Markdown из HTML справки |
| **`build-index <directory> [--incremental]`** | Построить векторный индекс в Qdrant по .md/.html |
| **`ingest`** | Распаковать .hbk из мультикаталогов во временную папку, построить Markdown, проиндексировать в Qdrant, удалить временные данные |
| **`index-status`** | Показать статус индекса (число тем, версии, языки) |
| **`serve <directory>`** | Веб-просмотр справки (Flask) |
| **`mcp <directory>`** | MCP-сервер (stdio/HTTP; нужен fastmcp) |

Переменные окружения: `QDRANT_HOST`, `QDRANT_PORT`, `HELP_PATH`, `PORT`, `MCP_TRANSPORT`, `HELP_SOURCE_BASE`, `HELP_LANGUAGES`, `HELP_INGEST_TEMP`.

## Запуск из коробки (Docker Compose)

Данные справки берутся через **ingest**: монтируется один каталог (`HELP_SOURCE_BASE=/opt/1cv8`), в нём каждая подпапка считается версией 1С и сканируется автоматически. Поиск .hbk рекурсивный, в т.ч. в подпапке `bin/` (на Windows: `C:\Program Files\1cv8\8.3.27.1859\bin`).

**macOS (Docker Desktop):** по умолчанию Docker не имеет доступа к `/opt`. Откройте **Docker Desktop → Settings (⚙️) → Resources → File sharing** и добавьте путь **`/opt`** (или **`/opt/1cv8`**). Нажмите **Apply & Restart**.

**Путь к .hbk:** на Linux/macOS часто `/opt/1cv8/8.3.27.1859/1cv8_ru.hbk`; на Windows — `...\8.3.27.1859\bin\1cv8_ru.hbk`. Ingest ищет `.hbk` рекурсивно, оба варианта поддерживаются.

### Быстрый старт

```bash
docker compose up -d
# База Qdrant хранится в ./data/qdrant (в проекте, при перезапуске не теряется)
# MCP: http://localhost:5050/mcp (подключить в Cursor через .cursor/mcp.json)
# Индексация вручную: docker compose exec mcp python -m onec_help ingest
# Проверка индекса: docker compose exec mcp python -m onec_help index-status
# По расписанию: в контейнере mcp запущен cron — раз в сутки в 3:00 переиндексация из /opt/1cv8
```

### Контейнер только для распаковки

Чтобы **только распаковать** .hbk в свою директорию (без индексации), используйте сервис **unpack** вручную:

```bash
# Смонтировать каталог с 1С и папку для результата; распаковать все .hbk в неё
docker compose run --rm \
  -v /opt/1cv8:/input:ro \
  -v $(pwd)/unpacked:/output \
  -e HELP_SOURCE_BASE=/input \
  -e HELP_LANGUAGES=ru \
  unpack
```

Структура выхода: `output/<версия>/<язык>/<имя_архива>/` (например `unpacked/8.3.27.1859/ru/1cv8_ru/`). Только распаковка, конвертация в Markdown и индексация не выполняются.

Локально та же логика:

```bash
python -m onec_help unpack-dir /opt/1cv8 -o ./unpacked -l ru
```

### Мультикаталоги (ingest): несколько версий 1С

Исходные каталоги **не изменяются**: из них читаются только `*.hbk`, распаковка и временные файлы — только внутри контейнера, после индексации всё удаляется.

**Из коробки** монтируется `/opt/1cv8` (только чтение). Ingest просматривает подпапки (`8.3.27.1859`, `8.3.27.1719`) и считает каждую версией 1С. Язык по имени файла (`*_ru.hbk` и т.д.): по умолчанию `HELP_LANGUAGES=ru`.

- **При старте контейнера:** если смонтирован `/opt/1cv8`, ingest один раз запускается **в фоне** (логи: `docker compose exec mcp tail -f /var/log/ingest.log`).
- **Вручную:** `docker compose exec mcp python -m onec_help ingest`
- **По расписанию:** cron в контейнере mcp — раз в сутки в 3:00.

Дополнительно:

```bash
docker compose exec mcp python -m onec_help ingest --workers 4
docker compose exec mcp python -m onec_help ingest --dry-run   # сколько .hbk будет обработано
docker compose exec mcp python -m onec_help ingest --max-tasks 1  # ограничить объём за один запуск
```

**Сколько топиков:** полная справка (один 1cv8_ru.hbk) — обычно 10–25 тыс. страниц. Проверка индексации: `docker compose exec mcp python -m onec_help index-status` или MCP **get_1c_help_index_status** (локально: `python -m onec_help index-status`).

**Таймаут:** полная индексация может занимать 15–60 минут. Запуск в фоне:

```bash
docker compose exec -d mcp sh -c 'python -m onec_help ingest >> /var/log/ingest.log 2>&1'
docker compose exec mcp tail -f /var/log/ingest.log
```

### Один контейнер без Compose

Только MCP (Qdrant на хосте):

```bash
docker run --rm -d -p 5050:5050 \
  -v /opt/1cv8:/opt/1cv8:ro \
  -e QDRANT_HOST=host.docker.internal \
  -e QDRANT_PORT=6333 \
  -e HELP_SOURCE_BASE=/opt/1cv8 \
  --name onec-help-mcp \
  $(docker build -q .) \
  /app/entrypoint.sh python -m onec_help mcp /data --transport http --host 0.0.0.0 --port 5050
```

MCP: http://localhost:5050/mcp.

## MCP

| Инструмент | Назначение |
|------------|------------|
| **search_1c_help** | Семантический поиск по справке. |
| **search_1c_help_keyword** | Поиск по вхождению строки (точные термины: «МенеджерКриптографии», параметры запуска). |
| **get_1c_help_topic** | Полный текст темы по пути (с диска или из Qdrant). |
| **get_1c_function_info** | Описание функции/метода 1С по имени. |
| **list_1c_help_titles** | Список заголовков и путей; фильтр по началу пути (например `zif`). |
| **get_1c_help_index_status** | Статус индекса: число тем, версии, языки. |

**Рекомендация:** для точных имён — сначала **search_1c_help_keyword**; для общих вопросов — **search_1c_help**.

Конфиг Cursor: **`.cursor/mcp.json`** (пример — `docs/mcp.json.example`). MCP по HTTP (порт 5050). После правок конфига Cursor перезапускают.

**Если Cursor пишет «connect ECONNREFUSED 127.0.0.1:5050»:** проверьте `docker compose up -d`, `docker compose ps`, `docker compose logs mcp`.

## Тесты и линт

```bash
pip install -e ".[dev]"
PYTHONPATH=src python -m pytest tests -v --cov=src/onec_help --cov-report=term-missing --cov-fail-under=90
ruff check src tests && ruff format --check src tests
```

Покрытие не менее 90% (в расчёт не входят `__main__.py` и `mcp_server.py`).

## CI (GitHub Actions)

- **test** — pytest, покрытие ≥90%, матрица Python 3.10–3.12.
- **lint** — ruff check и ruff format.
- **deploy** — сборка и push Docker-образа в GHCR (при push в main/master или вручную).
- **release** — при push тега `v*`: сборка sdist и создание GitHub Release; отдельно — сборка и push Docker-образа с тегом версии.

## Документация

- [docs/run.md](docs/run.md) — запуск локально и в Docker.
- [docs/search-and-mcp.md](docs/search-and-mcp.md) — поиск и рекомендации по MCP.
- [docs/help_formats.md](docs/help_formats.md) — форматы справки (.hbk, HTML, Markdown).
- [docs/mcp.json.example](docs/mcp.json.example) — пример конфига MCP для Cursor.

## Дальнейшие этапы

Планируются MCP по кодовой базе и метаданным 1С (индексированный поиск по коду, подсказки по разработке). Структура репозитория допускает добавление сервисов `mcp-codebase` и `mcp-metadata` в compose.
