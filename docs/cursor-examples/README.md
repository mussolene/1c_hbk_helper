# Cursor: skills и rules (эталон в репозитории)

Каталог **`docs/cursor-examples/`** — единственная копия в git. Папка **`.cursor/`** не коммитится (см. `.gitignore`); после клонирования или обновления скиллов скопируйте отсюда в свой `.cursor/`.

## Синхронизация в локальный `.cursor/skills/`

Из корня репозитория:

```bash
for d in 1c-explain-object 1c-mcp-development 1c-mcp-token-budget 1c-mcp-tools-report; do
  mkdir -p .cursor/skills/$d
  rsync -a --delete "docs/cursor-examples/$d/" ".cursor/skills/$d/"
done
```

Правила (`.mdc`):

```bash
mkdir -p .cursor/rules
cp docs/cursor-examples/rules/*.mdc .cursor/rules/
```

Обратное копирование (если правили только локально): скопируйте изменённый файл в `docs/cursor-examples/...` и закоммитьте.

## Skills

| Каталог | Назначение |
|---------|------------|
| `1c-mcp-development/` | Основной workflow: MCP onec-context-mcp, тесты Python, метаданные. См. `reference.md`. |
| `1c-mcp-token-budget/` | Порядок вызовов MCP, экономия контекста, шпаргалки по СКД. |
| `1c-mcp-tools-report/` | Как читать отчёт о полноте инструментов MCP. |
| `1c-explain-object/` | Авто-документирование объектов конфигурации. |

## Rules (`rules/*.mdc`)

Краткие правила для контекста: конвенции проекта, workflow MCP, тесты, BSL и источники справки. Копируйте в `.cursor/rules/` (см. выше).

## Связь с документацией проекта

- [mcp-tools-reference.md](../reference/mcp-tools-reference.md) — параметры инструментов (канон при расхождении с кэшем Cursor).
- [mcp-cursor-tool-schemas/](../reference/mcp-cursor-tool-schemas/README.md) — снимки схем для частых ошибок валидации.

## Зависимость для разработчиков репозитория

При изменении MCP или этих скиллов — обновляйте **`docs/cursor-examples/`** и при необходимости выполняйте синхронизацию у себя в `.cursor/`.
