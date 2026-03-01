# Сниппеты (загружаются в память MCP)

В Docker: ./data/snippets → /data/snippets. parse-fastcode и parse-helpf пишут туда. HelpF по умолчанию — только FAQ. Локально: data/snippets/.

Формат: `*.bsl`, `*.1c`, `*.md` или `*.json` (массив `{title, description, code_snippet?, instruction?}`). Snippets (с кодом) → domain=snippets. References (справочный материал) → domain=community_help с полем `instruction` (полный текст).

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
make parse-helpf             # парсинг HelpF FAQ (по умолчанию) → helpf_snippets.json
make load-snippets           # загрузка в память
```

По умолчанию — FAQ, автоопределение страниц. HelpF полностью (file, forum, freelance): `--source all`. Ограничить: `make parse-helpf ARGS='--pages 1-5 --max-items 50 --no-fetch-detail'`.
