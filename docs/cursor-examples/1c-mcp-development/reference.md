# Reference: 1C MCP Development

## URI Mapping (Host ↔ Container)

When bsl-bridge runs in Docker with `.:/projects`:

| Host path | Container URI (for document_diagnostics) |
|-----------|------------------------------------------|
| `./src/.../Module.bsl` | `file:///projects/src/.../Module.bsl` |
| `./DataProcessors/X/Module.bsl` | `file:///projects/DataProcessors/X/Module.bsl` |

Rule: host `./` maps to `/projects`; prefix with `file://`.

## Example document_diagnostics Call

```
document_diagnostics(
  uri="file:///projects/src/DataProcessors/.../Forms/.../Ext/Form/Module.bsl"
)
```

## Example get_1c_help_topic Call

```
get_1c_help_topic(topic_path="Format971.md")
```

Do **not** use `path` — the parameter is `topic_path`.

## Example search_1c_help_keyword Call

```
search_1c_help_keyword(query="ФайловыеОперации.НачатьУдалениеФайлов")
```

Use full qualified names for types and methods.

## Example get_form_metadata Call

Read Form.xml, then pass its content:

```
# 1. Read the file (e.g. .nosync/.../Forms/X/Ext/Form.xml)
# 2. Call with xml_content
get_form_metadata(xml_content="<Form ...>...</Form>")
```

## Example save_1c_snippet Call

```
save_1c_snippet(
  code_snippet="...",
  description="Удаление временных файлов через НачатьУдалениеФайлов",
  title="УдалениеФайлов"
)
```

## BSL LS Diagnostics Without Quick-Fix

Many BSL LS diagnostics (e.g. SemicolonPresence, LineLength) do not have `code_actions` quick-fix. Fix manually:

- Add semicolon after `ВызватьИсключение "..."`
- Split long lines or add `// BSLLS:LineLength-off` with a brief reason
- Use `#Область` / `#КонецОбласть` for structure

## Two MCPs Together

- **1c-help**: справка, сниппеты, память
- **lsp-bsl-bridge**: навигация, диагностика, рефакторинг

If 1c-help is unavailable (no index): rely on lsp-bsl-bridge and memory only.
