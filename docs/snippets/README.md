# Сниппеты 1С — примеры (не загружаются автоматически)

Эта папка содержит **примеры** форматов для справки. Они **не загружаются** в память MCP по умолчанию.

## Загрузка реальных сниппетов

Реальные сниппеты загружаются из **смонтированного тома** (read-only):

- **Docker Compose:** смонтируйте папку в `SNIPPETS_DIR` (по умолчанию `/data/snippets`)
- **docker run:** `-v /path/to/snippets:/data/snippets:ro`

Форматы: `*.bsl`, `*.1c`, `*.md` (YAML frontmatter + блок кода), `snippets.json`.

## Примеры в этой папке

- `snippets.json` — формат JSON (массив `{title, description, code_snippet}`)
- `examples/` — примеры файлов `*.bsl` для папочной загрузки
