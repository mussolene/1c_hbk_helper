# Cursor: Skill и Rules — примеры для индексации

Примеры Skill и Rules для Cursor, используемые при работе с 1c-help и lsp-bsl-bridge MCP.

## Назначение

- **Индексация:** содержимое `docs/cursor-examples/` в репозитории и доступно для поиска по кодовой базе; папка `.cursor/` полностью исключена из git (см. `.gitignore`).
- **Синхронизация:** при изменении поведения MCP или workflow в проекте обновите эти примеры — они служат эталоном и исходником для копирования в `.cursor/skills/` и `.cursor/rules/`.
- **Зависимость для доработки:** при доработке MCP, AGENTS.md или workflow разработки 1С проверьте соответствие с `docs/cursor-examples/` и при необходимости внесите правки.

## Структура

```
docs/cursor-examples/
├── README.md                 # Этот файл
├── 1c-mcp-development/       # Skill
│   ├── SKILL.md
│   └── reference.md
└── rules/                    # Rules (.mdc)
    ├── 1c-bsl-standards.mdc
    ├── 1c-mcp-workflow.mdc
    └── 1c-project-conventions.mdc
```

## Использование

1. **Копирование в .cursor:** при первом клонировании или настройке Cursor скопируйте:
   - `docs/cursor-examples/1c-mcp-development/` → `.cursor/skills/1c-mcp-development/`
   - `docs/cursor-examples/rules/*.mdc` → `.cursor/rules/`

2. **Обновление после изменений:** если вы изменили skill или rules в `.cursor/` и хотите зафиксировать их в репозитории — скопируйте обратно в `docs/cursor-examples/` и закоммитьте.

## Связь с проектом

- См. [AGENTS.md](../AGENTS.md) — workflow разработки 1С с BSL LS.
- См. [bsl-ls-mcp-setup.md](../bsl-ls-mcp-setup.md) — подключение BSL LS как MCP.
