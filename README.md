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
- **`ingest`** — мультикаталоги: из нескольких **только для чтения** каталогов собрать все .hbk, распаковать во временную папку в контейнере, построить Markdown, проиндексировать в Qdrant с полями `version` и `language`, затем удалить временные данные. Поддерживается фильтр по языку (по умолчанию из `HELP_LANGUAGES=ru`; если не задан — все языки) и параллельная обработка (`--workers`).
- **`serve <directory>`** — запустить веб-просмотр справки (Flask)
- **`mcp <directory>`** — запустить MCP-сервер (stdio; нужен fastmcp)

Переменные окружения: `QDRANT_HOST`, `QDRANT_PORT`, `HELP_PATH`, `PORT`, `MCP_TRANSPORT`, `HELP_SOURCE_BASE`, `HELP_LANGUAGES`, `HELP_INGEST_TEMP`.

## Запуск из коробки (Docker Compose)

Данные справки берутся через **ingest**: монтируется один каталог (`HELP_SOURCE_BASE=/opt/1cv8`), в нём каждая подпапка считается версией 1С и сканируется автоматически. Поиск .hbk рекурсивный, в т.ч. в подпапке `bin/` (на Windows: `C:\Program Files\1cv8\8.3.27.1859\bin`).

**macOS (Docker Desktop):** по умолчанию Docker не имеет доступа к `/opt`. Если у вас 1С в `/opt/1cv8/8.3.27.1719` и т.п., откройте **Docker Desktop → Settings (⚙️) → Resources → File sharing** и добавьте путь **`/opt`** (или только **`/opt/1cv8`**). Нажмите **Apply & Restart**. После этого `docker compose up -d` сможет примонтировать `/opt/1cv8`.

**Путь к .hbk:** на Linux/macOS файлы справки лежат в каталоге версии **без** подпапки `bin/`, например `/opt/1cv8/8.3.27.1859/1cv8_ru.hbk`. На Windows часто `...\8.3.27.1859\bin\1cv8_ru.hbk`. Ingest ищет `.hbk` рекурсивно, так что оба варианта поддерживаются.

### Быстрый старт

   ```bash
   docker compose up -d
   # MCP: http://localhost:5050/mcp (подключить в Cursor через .cursor/mcp.json)
   # Индексация вручную: docker compose exec mcp python -m onec_help ingest
   # По расписанию: в контейнере mcp запущен cron — раз в сутки в 3:00 переиндексация из /opt/1cv8
   ```

### Мультикаталоги (ingest): несколько версий 1С, только чтение, очистка после

Исходные каталоги **не изменяются**: из них читаются только файлы `*.hbk`, распаковка и временные файлы — только внутри контейнера, после индексации всё удаляется.

**Из коробки в compose** монтируется один каталог `/opt/1cv8` (только чтение). Ingest просматривает в нём подпапки (например `8.3.27.1859`, `8.3.27.1719`) и считает каждую подпапку отдельной версией 1С — дублировать список в конфиге не нужно. На Windows при монтировании укажите каталог установки 1С (например `C:\Program Files\1cv8`); внутри версий может быть подпапка `bin` — .hbk ищутся рекурсивно.

Язык по имени файла (`*_ru.hbk` и т.д.): по умолчанию `HELP_LANGUAGES=ru` — только русские справки; если переменную не задавать — индексируются все языки.

Запуск индексации:

   - **При старте контейнера:** если смонтирован `/opt/1cv8`, ingest один раз запускается **в фоне** (логи: `docker compose exec mcp tail -f /var/log/ingest.log`). MCP при этом стартует сразу.
   - **Вручную:** `docker compose exec mcp python -m onec_help ingest` (смонтированный `/opt/1cv8` пересканируется, .hbk распаковываются во временную папку в контейнере, индекс в Qdrant обновляется).
   - **По расписанию:** в контейнере **mcp** запущен **cron** — раз в сутки в **3:00** выполняется тот же ingest (расписание в `crontab` в корне репозитория).

   Если 1С установлена в `/opt/1cv8`, подпапки считаются версиями и индексируются. Свой каталог: задайте `HELP_SOURCE_BASE` и смонтируйте его в volumes для mcp.

   Дополнительно:

   ```bash
   docker compose exec mcp python -m onec_help ingest --workers 4
   docker compose exec -e HELP_SOURCE_BASE=/other/1cv8 mcp python -m onec_help ingest
   # Сколько архивов будет обработано (без распаковки):
   docker compose exec mcp python -m onec_help ingest --dry-run
   # Размер порции индексации (по умолчанию 500 файлов за раз):
   docker compose exec mcp python -m onec_help ingest --index-batch-size 500
   ```

   **Какие файлы попадают в индекс:** при распаковке .hbk извлекаются **все** файлы (в т.ч. из подпапок вроде PayloadData, FileStorage и т.п.). В Markdown конвертируются: **.html**, **.htm**, файлы **без расширения** и **.xml/.xhtml/.st**, если содержимое похоже на HTML. Остальные (картинки, .css, .js, .db и т.д.) не обрабатываются. Папки по имени не пропускаются — обход рекурсивный по всем каталогам.

   **Сколько топиков должно быть:** полная справка 1С (один архив 1cv8_ru.hbk) обычно даёт **10–25 тыс.** страниц. Если в индексе всего 1–2 тыс., скорее всего обработан только один .hbk или индексация прервалась. Проверка: **get_1c_help_index_status** (MCP) или `python -m onec_help index-status`; сколько архивов будет обработано: `python -m onec_help ingest --dry-run`.

   **Таймаут при ручном запуске:** полная индексация (несколько .hbk, эмбеддинги) может занимать **15–60 минут**. Если `docker compose exec ... ingest` обрывается по таймауту:

   - Запускайте ingest **в фоне** (логи в файл):
     ```bash
     docker compose exec -d mcp sh -c 'python -m onec_help ingest >> /var/log/ingest.log 2>&1'
     docker compose exec mcp tail -f /var/log/ingest.log
     ```
   - Или ограничьте объём за один запуск и вызывайте несколько раз:
     ```bash
     docker compose exec mcp python -m onec_help ingest --max-tasks 1
     docker compose exec mcp python -m onec_help ingest --max-tasks 2
     ```
   - Прогресс по умолчанию выводится в stderr (`[ingest] ...`) — при длительном запуске без `-d` это снижает риск обрыва по «нет вывода».

   В индекс в Qdrant попадают поля `version` и `language` — по ним можно фильтровать поиск по версии и языку.


### Один контейнер без Compose

Запуск только MCP (подключиться к Qdrant на хосте):

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

   MCP: http://localhost:5050/mcp. Qdrant на хосте — порт 6333.

## MCP

Инструменты:

| Инструмент | Назначение |
|------------|------------|
| **search_1c_help** | Семантический поиск по справке (запрос на естественном языке). |
| **search_1c_help_keyword** | Поиск по вхождению строки в заголовок и текст (например «МенеджерКриптографии», «интерактивный режим»). Использовать, когда семантический поиск не находит точный термин. |
| **get_1c_help_topic** | Получить полный текст темы по пути из результатов поиска. Контент берётся с диска или из индекса Qdrant, если файлы не сохранялись. |
| **get_1c_function_info** | Описание функции/метода 1С по имени (сначала ключевой поиск, затем семантический). |
| **list_1c_help_titles** | Список заголовков и путей для просмотра; опционально фильтр по началу пути (например `zif` — параметры командной строки). |
| **get_1c_help_index_status** | Проверить, проиндексирована ли справка: число тем, имя коллекции, версии и языки (по выборке). |

**Проверка индекса:** вызовите **get_1c_help_index_status** в MCP или в терминале: `docker compose exec mcp python -m onec_help index-status`.

**Рекомендация:** для точных имён (МенеджерКриптографии, параметры запуска и т.п.) сначала вызывайте **search_1c_help_keyword**; для общих вопросов — **search_1c_help**.

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
