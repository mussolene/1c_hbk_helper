# 1C Help — MCP в Docker

[![Test](https://github.com/mussolene/1c_hbk_helper/actions/workflows/test.yml/badge.svg)](https://github.com/mussolene/1c_hbk_helper/actions/workflows/test.yml)
[![Lint](https://github.com/mussolene/1c_hbk_helper/actions/workflows/lint.yml/badge.svg)](https://github.com/mussolene/1c_hbk_helper/actions/workflows/lint.yml)
[![Lint Commits](https://github.com/mussolene/1c_hbk_helper/actions/workflows/commitlint.yml/badge.svg)](https://github.com/mussolene/1c_hbk_helper/actions/workflows/commitlint.yml)
[![Coverage](https://codecov.io/gh/mussolene/1c_hbk_helper/graph/badge.svg)](https://codecov.io/gh/mussolene/1c_hbk_helper)
[![Release](https://github.com/mussolene/1c_hbk_helper/actions/workflows/release.yml/badge.svg)](https://github.com/mussolene/1c_hbk_helper/releases)


Справка 1С: распаковка .hbk (7z), конвертация в Markdown, индексация в Qdrant, MCP-сервер для поиска и чтения справки.

Контрибьюторам: см. [CONTRIBUTING.md](CONTRIBUTING.md) (формат коммитов — Conventional Commits).

Лицензия проекта: MIT, см. [LICENSE](LICENSE). Используемые библиотеки и лицензии: см. [NOTICE](NOTICE).

Стандарты разработки 1С (load-standards): по умолчанию загружаются совместно [1C-Company/v8-code-style](https://github.com/1C-Company/v8-code-style) и [zeegin/v8std](https://github.com/zeegin/v8std) ([v8std.ru](https://v8std.ru)).

## Безопасность

- **Веб (serve)** и **MCP по HTTP** не имеют встроенной аутентификации. Предназначены **только** для доверенной среды (localhost, VPN, внутренняя сеть). При экспозиции в интернет — обязателен обратный прокси с аутентификацией.
- Не выставляйте порты 5000 (Flask) и 5050 (MCP) в интернет без обратного прокси с аутентификацией (nginx + Basic Auth, API key и т.п.).
- **HELP_SERVE_ALLOWED_DIRS** — обязательна для serve: без неё форма просмотра справки не принимает пути (защита от чтения произвольных каталогов). Задайте список разрешённых базовых каталогов через запятую.
- Секреты и пароли задавайте только через переменные окружения, не храните в коде или в репозитории.
- CLI (аргументы `--sources-file`, пути к каталогам) предназначен для доверенного запуска; не передавайте недоверенный ввод в аргументы.

### Конфиденциальность и NDA

- **Embedding API:** текст справки и поисковые запросы отправляются на внешний сервис. При NDA или конфиденциальных данных используйте on-prem сервис (EMBEDDING_API_URL на внутренний хост).
- **Memory и сниппеты:** хранятся на диске и в Qdrant; настройте пути в защищённое место при работе с конфиденциальным кодом.

## Требования

- Python 3.14+ (в образе Docker используется python:3.14-slim; при несовместимости зависимостей можно понизить до 3.12)
- Docker и docker-compose (для контейнерного запуска)
- 7z (p7zip-full) — для распаковки .hbk внутри контейнера

## Установка (локально)

```bash
pip install -e .
# С поддержкой MCP (Python 3.10+):
pip install -e ".[mcp]"
# Локальные эмбеддинги (EMBEDDING_BACKEND=local): добавьте extra [embed]
pip install -e ".[mcp,embed]"
# Для тестов и линтера:
pip install -e ".[dev]"
```

Без `[embed]` при `local` будет использоваться плейсхолдер (как при `none`). При `openai_api` или `none` extra `[embed]` не нужен.

## Команды CLI

| Команда | Описание |
|--------|----------|
| **`unpack <archive> [--output-dir]`** | Распаковать один .hbk (7z → zipfile → offset → unzip → scan local headers) |
| **`unpack-diag <archive> [-o dir]`** | Диагностика распаковки: пробует каждый метод, печатает результат (при «All unpack methods failed») |
| **`unpack-dir [source_dir] [-o output]`** | Распаковать все .hbk из дерева каталогов в указанную директорию (без индексации). Источники: `source_dir`, `HELP_SOURCE_BASE` или `--sources` |
| **`build-docs <project_dir> [--output]`** | Сгенерировать Markdown из HTML справки |
| **`build-index <directory> [--incremental] [--embedding-batch-size N] [--embedding-workers N]`** | Построить векторный индекс в Qdrant по .md/.html (батч-эмбеддинги; при openai_api — параллельные запросы) |
| **`ingest`** | Распаковать .hbk из мультикаталогов во временную папку, построить Markdown, проиндексировать в Qdrant, удалить временные данные. По хэшу .hbk кэшируется факт индексации — при перезапуске неизменённые файлы пропускаются (не парсятся, не пересчитываются эмбеддинги). Опции `--no-cache` для полной переиндексации; `--embedding-batch-size`, `--embedding-workers` — для ускорения эмбеддингов |
| **`index-status`** | Статус индекса: число тем, число эмбеддингов, размер БД на диске (если задан `QDRANT_STORAGE_PATH`), версии и языки; при запущенном ingest — скорость эмбеддингов, прогресс по папкам, ETA |
| **`watchdog`** | Мониторинг новых .hbk в HELP_SOURCE_BASE, инкрементальный ingest при появлении; обработка pending embeddings памяти каждые N минут |
| **`serve <directory>`** | Веб-просмотр справки (Flask) |
| **`mcp <directory>`** | MCP-сервер (stdio/HTTP; нужен fastmcp) |

Переменные окружения (подробнее — см. таблицу ниже): `QDRANT_HOST`, `QDRANT_PORT`, `QDRANT_COLLECTION`, `HELP_PATH`, `HELP_SOURCE_BASE`, `HELP_SOURCES_DIR`, `HELP_SOURCE_DIRS`, `HELP_LANGUAGES`, `HELP_INGEST_TEMP`, `INGEST_FAILED_LOG`, `MCP_TRANSPORT`, `MCP_HOST`, `MCP_PORT`, `MCP_PATH`, `PORT`.

| Переменная | Описание | Пример / по умолчанию |
|------------|----------|------------------------|
| `QDRANT_HOST` | Хост Qdrant | `localhost` |
| `QDRANT_PORT` | Порт Qdrant | `6333` |
| `QDRANT_COLLECTION` | Имя коллекции в Qdrant | `onec_help` |
| `QDRANT_STORAGE_PATH` | Путь к каталогу хранилища Qdrant (для `index-status`: вывод размера БД на диске) | — |
| `HELP_PATH` | Базовый каталог справки (для MCP/serve) | `/data` |
| `HELP_SOURCE_BASE` | Корень каталогов с версиями 1С (ingest) | — |
| `HELP_SOURCES_DIR` | То же, альтернативное имя | — |
| `HELP_SOURCE_DIRS` | Список путей через запятую (ingest) | — |
| `HELP_LANGUAGES` | Языки справки (ingest) | `ru` |
| `HELP_INGEST_TEMP` | Временный каталог для ingest (если не задан — `$TMPDIR/help_ingest` или `tempfile.gettempdir()`) | — |
| `HELP_SERVE_HOST` | Хост для serve (127.0.0.1 — только localhost; 0.0.0.0 — для Docker) | `127.0.0.1` |
| `INGEST_CACHE_FILE` | Путь к SQLite-кэшу ingest (хэш .hbk → уже проиндексировано; при перезапуске не перепарсивать и не пересчитывать embedding). В Docker по умолчанию `/qdrant_storage/ingest_cache.db` | `/tmp/onec_help_ingest_cache.db` |
| `INGEST_SKIP_CACHE` | `1`/`true` — полная переиндексация без кэша (или `ingest --no-cache`) | — |
| `INGEST_FAILED_LOG` | Файл для списка неудачных .hbk | — |
| `MCP_TRANSPORT` | Транспорт MCP: `stdio`, `http` или `streamable-http` (для Docker/Cursor рекомендуется streamable-http) | `streamable-http` |
| `MCP_HOST` | Хост для MCP HTTP | `127.0.0.1` |
| `MCP_PORT` | Порт для MCP HTTP | `5050` |
| `MCP_PATH` | URL-путь эндпоинта MCP | `/mcp` |
| `PORT` | Порт веб-сервера (serve) | `5000` |
| `SERVE_PORT` | Порт serve в Docker (split, профиль serve) | `5000` |
| `HELP_SERVE_ALLOWED_DIRS` | Список путей через запятую (serve): разрешённые базовые каталоги для формы; если задан, ввод вне списка отклоняется | — |
| `EMBEDDING_BACKEND` | Эмбеддинги: `local` (sentence-transformers), `openai_api` (внешний API), `deterministic` (детерминированные векторы 384 dim без модели — только БД) или `none` (плейсхолдер, только поиск по ключевым словам) | `openai_api` |
| `EMBEDDING_MODEL` | Имя модели. Для openai_api (LM Studio): если такой модели нет на сервере, берётся первая из списка или популярная (text-text-embedding-mxbai-embed-large-v1, nomic-embed-text, all-MiniLM-L6-v2); для local — all-MiniLM-L6-v2 | `text-text-embedding-mxbai-embed-large-v1` (openai_api) |
| `EMBEDDING_API_URL` | Для openai_api: базовый URL (по умолчанию LM Studio: `http://localhost:1234/v1` локально, в контейнере — `http://host.docker.internal:1234/v1`). При недоступности/ошибках используются плейсхолдер-векторы и семантический поиск ограничен | LM Studio: 1234 |
| `EMBEDDING_API_KEY` | Ключ API (если нужен для openai_api) | — |
| `EMBEDDING_DIMENSION` | Размерность при openai_api (если не задана — определяется по первому ответу API) | — |
| `EMBEDDING_BATCH_SIZE` | Размер батча для эмбеддингов (текстов за один вызов encode/API). По умолчанию 64 | `64` |
| `EMBEDDING_WORKERS` | Число параллельных запросов к внешнему API (только openai_api). По умолчанию 4 | `4` |
| `EMBEDDING_FORCE_BATCH` | Максимальная мощность: `1`/`true`/`yes` — батч 256 и 16 воркеров для любого типа embedding | — |
| `EMBEDDING_MAX_CONCURRENT` | Макс. одновременных запросов к API (при ingest с несколькими воркерами снижает перегрузку LM Studio) | — |
| `EMBEDDING_TIMEOUT` | Таймаут HTTP-запроса к API (секунды). При ошибке — retry с backoff, затем плейсхолдер | `60` |
| `EMBEDDING_BATCH_TIMEOUT` | Таймаут для batch-запроса (секунды). По умолчанию — формула от размера батча | — |
| `MCP_MODE` | `api` — только MCP (split, по умолчанию); `full` — всё в mcp (один контейнер) | `api` |
| `WATCHDOG_ENABLED` | `1` — запустить watchdog в фоне: мониторинг .hbk и обработка pending memory | `0` |
| `WATCHDOG_POLL_INTERVAL` | Интервал проверки новых .hbk (секунды) | `600` |
| `WATCHDOG_PENDING_INTERVAL` | Интервал обработки pending embeddings (секунды) | `600` |

## Запуск из коробки (Docker Compose)

Данные справки берутся через **ingest**: монтируется один каталог (`HELP_SOURCE_BASE=/opt/1cv8`), в нём каждая подпапка считается версией 1С и сканируется автоматически. Поиск .hbk рекурсивный, в т.ч. в подпапке `bin/` (на Windows: `C:\Program Files\1cv8\8.3.27.1859\bin`).

**macOS (Docker Desktop):** по умолчанию Docker не имеет доступа к `/opt`. Откройте **Docker Desktop → Settings (⚙️) → Resources → File sharing** и добавьте путь **`/opt`** (или **`/opt/1cv8`**). Нажмите **Apply & Restart**.

**Путь к .hbk:** на Linux/macOS часто `/opt/1cv8/8.3.27.1859/1cv8_ru.hbk`; на Windows — `...\8.3.27.1859\bin\1cv8_ru.hbk`. Ingest ищет `.hbk` рекурсивно, оба варианта поддерживаются.

### Быстрый старт

```bash
docker compose up -d
# База Qdrant хранится в ./data/qdrant (в проекте, при перезапуске не теряется).
# В docker-compose хранилище смонтировано в mcp как /qdrant_storage (QDRANT_STORAGE_PATH) — index-status показывает размер БД.
# MCP: http://localhost:5050/mcp (подключить в Cursor через .cursor/mcp.json)
# Индексация вручную: make ingest
# Проверка индекса: docker compose exec mcp python -m onec_help index-status
```

### Режимы развёртывания

**Split (по умолчанию)** — `mcp` только MCP API (быстрый отклик), `ingest-worker` — batch (ingest, cron, load-snippets, watchdog). Рекомендуется для большинства сценариев.

```bash
docker compose up -d
make ingest   # индексация вручную
```

**Split + serve** — дополнительно веб-просмотр справки (Flask, порт 5000). Требуется `./data/unpacked` с распакованной справкой.

```bash
docker compose --profile serve up -d
```

**Full** — один контейнер `mcp` выполняет всё: MCP API, ingest, cron, watchdog. Подходит для локальной разработки или малой нагрузки.

```bash
docker compose -f docker-compose.full.yml up -d
# или: make up-full
# Индексация: make ingest-full
```

**Пересборка при изменениях:** `make build && make up` (сборка образов, затем запуск). Full: `make build-full && make up-full`. Подробнее — [docs/architecture.md](docs/architecture.md).

### Только распаковка .hbk (выгрузка справки в папку)

Чтобы **только распаковать** .hbk в свою директорию (без индексации и MCP):

```bash
make unpack-help
# или с параметрами:
make unpack-help HELP_SOURCE_PATH=/opt/1cv8 UNPACK_OUTPUT=data/unpacked HELP_LANGS=ru
```

Либо напрямую:

```bash
docker compose run --rm \
  -v /opt/1cv8:/input:ro \
  -v $(pwd)/data/unpacked:/output \
  mcp python -m onec_help unpack-dir /input -o /output -l ru
```

Структура выхода: `output/<версия>/<язык>/<имя_архива>/` (например `unpacked/8.3.27.1859/ru/1cv8_ru/`). Только распаковка, конвертация в Markdown и индексация не выполняются.

Локально та же логика:

```bash
python -m onec_help unpack-dir /opt/1cv8 -o ./unpacked -l ru
```

### Мультикаталоги (ingest): несколько версий 1С

Исходные каталоги **не изменяются**: из них читаются только `*.hbk`, распаковка и временные файлы — только внутри контейнера, после индексации всё удаляется.

**Из коробки** монтируется `/opt/1cv8` (только чтение). Ingest просматривает подпапки (`8.3.27.1859`, `8.3.27.1719`) и считает каждую версией 1С. Язык по имени файла (`*_ru.hbk` и т.д.): по умолчанию `HELP_LANGUAGES=ru`.

- **При старте (full):** если смонтирован `/opt/1cv8`, ingest один раз запускается в фоне (логи: `docker compose -f docker-compose.full.yml exec mcp tail -f /app/var/log/ingest.log`).
- **Вручную:** `make ingest` (split) или `make ingest-full` (full).
- **По расписанию:** cron в full-режиме — раз в сутки в 3:00; в split — настраивается в ingest-worker.
- **Watchdog** (при `WATCHDOG_ENABLED=1`): мониторинг новых .hbk в HELP_SOURCE_BASE; при появлении или изменении — полный ingest; каждые N минут — обработка pending memory (эмбеддинги, сохранённые при недоступном API). Логи: `tail -f /app/var/log/watchdog.log`.

Дополнительно:

```bash
make ingest ARGS="--workers 4"
make ingest ARGS="--dry-run"   # сколько .hbk будет обработано
make ingest ARGS="--max-tasks 1"  # ограничить объём за один запуск
make ingest ARGS="--recreate"  # пересоздать коллекцию (после смены модели/размерности)
make ingest ARGS="--no-cache"  # полная переиндексация без кэша
```

**Сколько топиков:** полная справка (один 1cv8_ru.hbk) — обычно 10–25 тыс. страниц. Проверка индексации: `docker compose exec mcp python -m onec_help index-status` или MCP **get_1c_help_index_status** (локально: `python -m onec_help index-status`).

**Таймаут:** полная индексация может занимать 15–60 минут. Запуск в фоне (split: ingest-worker; full: mcp):

```bash
docker compose exec -d ingest-worker sh -c 'python -m onec_help ingest >> /app/var/log/ingest.log 2>&1'
docker compose exec ingest-worker tail -f /app/var/log/ingest.log
```

### Эмбеддинги: отключение, локальная модель, внешний сервис

- **Отключение эмбеддингов** (`EMBEDDING_BACKEND=none`): семантический поиск отключён, в индекс пишутся плейсхолдер-векторы; поиск по смыслу не работает, но **search_1c_help_keyword** (по ключевым словам) и остальные инструменты MCP работают. Подходит для экономии ресурсов или когда нужен только поиск по строкам.
- **Deterministic** (`deterministic`): детерминированные векторы 384 dim без внешней модели — хэш от токенов текста. Семантический поиск ограничен, но воспроизводим. Без зависимостей.
- **Локальная модель** (`local`): sentence-transformers в контейнере. Нужна установка зависимостей для эмбеддингов (см. ниже).
- **Внешний API** (`openai_api`): LM Studio, Ollama, llama.cpp server и т.п. Задайте в `.env`:

```env
EMBEDDING_BACKEND=openai_api
EMBEDDING_API_URL=http://llama:8080/v1
EMBEDDING_MODEL=your-embedding-model
EMBEDDING_DIMENSION=768
```

Если сервис эмбеддингов в том же Compose, задайте `EMBEDDING_API_URL` по имени сервиса. Размерность вектора при openai_api определяется автоматически по первому ответу API; при смене модели пересоздайте коллекцию: `make ingest ARGS="--recreate"`.

**Нужно ли ставить зависимости для эмбеддингов (sentence-transformers), если используется сторонний сервис, `none` или `deterministic`?** Нет. При `openai_api`, `none` или `deterministic` sentence-transformers не используются. При сборке образа зависимости для эмбеддингов ставятся **только если** `EMBEDDING_BACKEND=local` (значение передаётся как build-arg). Если в `.env` задано `EMBEDDING_BACKEND=none`, `openai_api` или `deterministic`, при `docker compose build` образ будет собран без sentence-transformers — меньше по размеру:

```bash
# В .env: EMBEDDING_BACKEND=none  (или openai_api)
docker compose build
# или явно:
docker build --build-arg EMBEDDING_BACKEND=none -t onec-help .
```

Одна и та же переменная `EMBEDDING_BACKEND` задаёт и режим в рантайме, и необходимость установки зависимостей при сборке.

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
  /app/entrypoint.sh python -m onec_help mcp /data --transport streamable-http --host 0.0.0.0 --port 5050
```

MCP: http://localhost:5050/mcp.

## MCP

| Инструмент | Назначение |
|------------|------------|
| **search_1c_help** | Семантический поиск по справке. |
| **search_1c_help_keyword** | Поиск по вхождению строки (точные термины: имена API, параметры запуска). |
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

- **test** — pytest, покрытие ≥90%, матрица Python 3.10–3.12; отчёт загружается в Codecov (action v3, для публичного репо токен не нужен). Чтобы плашка Coverage отображала процент, один раз добавьте репозиторий на [codecov.io](https://codecov.io) (вход через GitHub).
- **lint** — ruff check и ruff format.
- **deploy** — сборка и push Docker-образа в GHCR (при push в main/master или вручную).
- **release** — при push тега `v*`: сборка sdist и создание GitHub Release; отдельно — сборка и push Docker-образа с тегом версии.

## Документация

- `make help` — все команды Makefile (unpack-help, up, ingest, up-full, ingest-full и др.)
- [docs/architecture.md](docs/architecture.md) — сервисы, режимы развёртывания (single/split), ответственность.
- [docs/embedding.md](docs/embedding.md) — embedding-пайплайн: бэкенды, batch/single, retry, 429, переменные окружения.
- [docs/run.md](docs/run.md) — запуск локально и в Docker.
- [docs/search-and-mcp.md](docs/search-and-mcp.md) — поиск и рекомендации по MCP.
- [docs/help_formats.md](docs/help_formats.md) — форматы справки (.hbk, HTML, Markdown).
- [docs/mcp.json.example](docs/mcp.json.example) — пример конфига MCP для Cursor.
- [docs/cursor-examples/](docs/cursor-examples/README.md) — Skill и Rules для Cursor (1c-help + BSL LS); эталон для индексации; при доработке MCP обновлять как зависимость.

## Дальнейшие этапы

Планируются MCP по кодовой базе и метаданным 1С (индексированный поиск по коду, подсказки по разработке). Структура репозитория допускает добавление сервисов `mcp-codebase` и `mcp-metadata` в compose.
