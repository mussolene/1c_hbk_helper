# 1C Help — MCP в Docker

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
# Для тестов:
pip install -e ".[dev]"
```

## Команды CLI

- **`unpack <archive> [--output-dir]`** — распаковать .hbk через 7z
- **`build-docs <project_dir> [--output]`** — сгенерировать Markdown из HTML справки (.html и файлы без расширения с HTML, например после распаковки .hbk)
- **`build-index <directory> [--incremental]`** — построить векторный индекс в Qdrant по всем .md в каталоге; если .md нет — по .html и по файлам без расширения с HTML-содержимым (распакованный .hbk). `--incremental` — добавить/обновить без пересоздания коллекции.
- **`serve <directory>`** — запустить веб-просмотр справки (Flask)
- **`mcp <directory>`** — запустить MCP-сервер (stdio; нужен fastmcp)

Переменные окружения: `QDRANT_HOST`, `QDRANT_PORT`, `HELP_PATH`, `PORT`, `MCP_TRANSPORT`.

## Куда положить справку (полный пример)

В проекте уже есть каталог **`help_data/`** — в него кладут **распакованную** справку (HTML, `__categories__` и т.д.). В контейнере он монтируется как `/data`.

### Полный пример с Docker Compose

1. Распакуйте .hbk в каталог `help_data` (локально или в контейнере):

   ```bash
   # Локально (нужен 7z: brew install 7-zip):
   python -m onec_help unpack /path/to/your/file.hbk -o ./help_data
   ```

   Или распаковать в контейнере (если .hbk лежит, например, в `./downloads/syntax.hbk`):

   ```bash
   docker compose run --rm -v "$(pwd)/downloads:/in:ro" app \
     python -m onec_help unpack /in/syntax.hbk -o /data
   ```

2. Запустите сервисы и при необходимости постройте индекс:

   ```bash
   docker compose up -d
   # Веб-просмотр: http://localhost:5001

   # Markdown и векторный индекс для MCP-поиска (все файлы в папке индексируются):
   docker compose exec app python -m onec_help build-docs /data -o /data/docs_md
   docker compose exec app python -m onec_help build-index /data/docs_md
   # При появлении новых файлов — перезапустить build-docs и build-index
   # или только build-index с --incremental (дополнит индекс без полной пересборки):
   docker compose exec app python -m onec_help build-index /data/docs_md --incremental
   ```

**Мультифайловая индексация:** все .md (и при отсутствии .md — .html) в каталоге и подкаталогах попадают в индекс. Автоматического слежения за папкой нет: чтобы учесть новые файлы, нужно вручную запустить `build-docs` и `build-index` (или `build-index --incremental` для дополнения без пересоздания коллекции).

Готово: справка в **`help_data/`**, контейнер видит её как `/data`.

### Один контейнер без Compose

Передать каталог с распакованной справкой с хоста и подключиться к уже запущенному Qdrant:

   ```bash
   docker run --rm -d -p 5001:5001 \
     -v /absolute/path/to/unpacked_help:/data \
     -e QDRANT_HOST=host.docker.internal \
     -e QDRANT_PORT=6333 \
     -e PORT=5001 \
     --name onec-help-app \
     $(docker build -q .) \
     python -m onec_help serve /data
   ```

   Веб-интерфейс: http://localhost:5001. Qdrant должен быть доступен на хосте на порту 6333.

## MCP

Инструменты: `search_1c_help`, `get_1c_help_topic`, `get_1c_function_info`.

Конфиг Cursor: **`.cursor/mcp.json`** (пример — `docs/mcp.json.example`). MCP работает **внутри контейнера** по HTTP (порт **5050**). После `docker compose up -d` Cursor подключается по URL `http://localhost:5050/mcp`. Для локального запуска без Docker — `scripts/run_mcp.sh` и Python 3.10+ с fastmcp. После правок конфига Cursor перезапускают.

**Если Cursor пишет «connect ECONNREFUSED 127.0.0.1:5050»:** убедитесь, что контейнеры запущены: `docker compose up -d`. Проверьте, что сервис `mcp` работает: `docker compose ps`; если контейнер `mcp` падает — смотрите логи: `docker compose logs mcp`.

## Тесты

```bash
pip install -e ".[dev]"
PYTHONPATH=src pytest tests --cov=src/onec_help --cov-report=term-missing --cov-fail-under=79
```

Целевое покрытие — не менее 90% (см. план); в конфиге задан порог 79% для прохождения сборки.

## Дальнейшие этапы

Планируются MCP по кодовой базе и метаданным 1С (индексированный поиск по коду, подсказки по разработке). Структура репозитория допускает добавление сервисов `mcp-codebase` и `mcp-metadata` в compose.
