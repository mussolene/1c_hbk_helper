# Реальные сниппеты (загружаются в память MCP)

Положите сюда файлы `*.bsl`, `*.1c`, `*.md` или `*.json` (массив `{title, description, code_snippet}`).

Эта папка монтируется в контейнер, при старте выполняется `load-snippets`.

Файлы:
- `skd_composition_result.json` — варианты получения результата СКД программно (в таблицу, табдок, JSON, обход наборов, схема из XML и т.п.)

Примеры форматов — в `docs/snippets/`.

## FastCode (через Docker)

```bash
make parse-fastcode          # парсинг → fastcode_snippets.json
make load-snippets           # загрузка в память
make snippets                # оба шага
```

Опции: `make parse-fastcode ARGS='--pages 1-5 --no-fetch-detail'`
