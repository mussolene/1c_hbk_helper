# Запуск 1C Help

## Локально

1. Установить зависимости: `pip install -e ".[dev]"` (и при необходимости `.[mcp]` для MCP).
2. Распаковать справку:
   - Один архив: `python -m onec_help unpack /path/to/file.hbk -o ./unpacked`
   - Все .hbk из каталога: `python -m onec_help unpack-dir /opt/1cv8 -o ./unpacked -l ru`
3. Сгенерировать Markdown:  
   `python -m onec_help build-docs ./unpacked -o ./docs_md`
4. Запустить Qdrant (Docker): `docker run -d -p 6333:6333 -v qdrant_data:/qdrant/storage qdrant/qdrant:v1.12.0`
5. Построить индекс:  
   `QDRANT_HOST=localhost QDRANT_PORT=6333 python -m onec_help build-index ./docs_md`
6. Веб-просмотр:  
   `python -m onec_help serve ./unpacked`
7. MCP локально (stdio или HTTP):  
   `python -m onec_help mcp ./unpacked` (stdio) или  
   `python -m onec_help mcp ./unpacked --transport streamable-http --host 0.0.0.0 --port 5050`

## Docker Compose

- Данные справки: монтируется `/opt/1cv8` в контейнер mcp, подпапки = версии 1С. Индексация вручную: `docker compose exec mcp python -m onec_help ingest`; по расписанию в mcp запущен cron (раз в сутки в 3:00). На Windows при монтировании `C:\Program Files\1cv8` учтите подпапку `bin` — поиск .hbk рекурсивный.
- `docker compose up -d` — поднимает Qdrant и MCP-сервер (mcp; в нём же cron для индексации).
- Порты: 5050 (MCP, streamable-http), 6333 (Qdrant).
- **Только распаковка:** сервис `unpack` (профиль `unpack`) — распаковывает все .hbk в смонтированную директорию без индексации. Пример:  
  `docker compose run --rm -v /opt/1cv8:/input:ro -v $(pwd)/unpacked:/output -e HELP_SOURCE_BASE=/input unpack`

## Подключение MCP к Cursor

MCP работает **в контейнере** по протоколу **streamable-http** (не stdio). В проекте уже есть **`.cursor/mcp.json`**:

- Сервер: `1c-help`, URL: `http://localhost:5050/mcp`.
- После `docker compose up -d` Cursor подключается к контейнеру по этому URL. Перезапустите Cursor после правок конфига.

Инструменты: `search_1c_help`, `get_1c_help_topic`, `get_1c_function_info`.
