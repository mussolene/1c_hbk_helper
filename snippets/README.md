# Реальные сниппеты (загружаются в память MCP)

Положите сюда файлы `*.bsl`, `*.1c`, `*.md` или `*.json` (массив `{title, description, code_snippet}`).

Эта папка монтируется в контейнер, при старте выполняется `load-snippets`.

При парсинге HelpF и FastCode контент автоматически делится на **сниппеты** (код) и **справочные инструкции** (текст). При загрузке: snippets → domain=snippets, reference → domain=community_help.

Файлы:
- `skd_composition_result.json` — варианты получения результата СКД программно (в таблицу, табдок, JSON, обход наборов, схема из XML и т.п.)

Примеры форматов — в `docs/snippets/`.

## FastCode (через Docker)

```bash
make parse-fastcode          # парсинг → fastcode_snippets.json
make load-snippets           # загрузка в память
make snippets                # оба шага
```

По умолчанию — автоопределение всех страниц. Ограничить: `make parse-fastcode ARGS='--pages 1-5 --no-fetch-detail'`

## HelpF.pro (через Docker)

```bash
make parse-helpf             # парсинг FAQ/Files → helpf_snippets.json
make load-snippets           # загрузка в память
```

По умолчанию — автоопределение страниц. Ограничить: `make parse-helpf ARGS='--source faq --pages 1-5 --max-items 50 --no-fetch-detail'`
