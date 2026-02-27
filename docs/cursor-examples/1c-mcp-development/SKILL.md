---
name: 1c-mcp-development
description: Guides the agent through 1C (BSL) development using 1c-help and lsp-bsl-bridge MCPs. Use when writing, refactoring, or reviewing 1C code, .bsl modules, or when the user mentions 1C, BSL, справка 1С, BSL LS.
---

# 1C Development with MCP

## When to Use

Apply this skill when:

- Generating 1C/BSL code (procedures, functions, form modules)
- Refactoring existing 1C code
- Running BSL LS diagnostics
- Searching 1C help for API usage
- Working with `.bsl`, `.1c`, or `Form.xml` files

## Tool Selection Matrix

| Scenario | MCP | Tool | Notes |
|----------|-----|------|-------|
| Examples, API usage | 1c-help | `get_1c_code_answer` | Prefer `code_only=True` when only code needed |
| Exact API name lookup | 1c-help | `search_1c_help_keyword` | Pass full name e.g. `Тип.Метод` |
| Topic details | 1c-help | `get_1c_help_topic` | Use `topic_path`, not `path` |
| Save useful code | 1c-help | `save_1c_snippet` | After generating working example |
| Diagnostics (one file) | lsp-bsl-bridge | `document_diagnostics` | URI: `file:///projects/<path>/Module.bsl` |
| Quick-fixes | lsp-bsl-bridge | `code_actions` | Limited coverage; many require manual fix |
| Navigation | lsp-bsl-bridge | `project_analysis`, `symbol_explore` | Before refactoring |
| Rename | lsp-bsl-bridge | `call_graph` → `prepare_rename` → `rename` | Check call graph first |
| After mass edits | lsp-bsl-bridge | `did_change_watched_files` | Notify LSP of changes |

## Workflows

### Generating Code

1. Call `get_1c_code_answer(query)` for examples
2. If insufficient: `search_1c_help_keyword("Exact.API.Name")` or `get_1c_help_topic(topic_path)`
3. Edit/adopt the code
4. If the result is reusable: `save_1c_snippet(code_snippet, description, title)`
5. Run `document_diagnostics(uri)` to verify

### Refactoring

1. Call `document_diagnostics(uri)` for the file
2. Prioritize: ERROR > WARNING > INFO
3. Fix issues (one file at a time)
4. Re-run `document_diagnostics` after edits
5. After multiple files: call `did_change_watched_files` so LSP re-indexes

### URI for document_diagnostics

When using bsl-bridge in Docker (volume `.:/projects`):

```
file:///projects/src/DataProcessors/.../Forms/.../Ext/Form/Module.bsl
```

Map host path to container: `./src/...` → `file:///projects/src/...` (volume `.:/projects`)

## Common Pitfalls

| Mistake | Fix |
|---------|-----|
| `get_1c_help_topic(path=...)` | Use `topic_path`, not `path` |
| `ПрочитатьJSON` returns Соответствие | Add `ПрочитатьВСоответствие=Истина` |
| `HTTPСоединение.Получить` on client | Server-only; use HTTPЗапрос or RPC |
| Search for `Метод` only | Pass full `Тип.Метод` in `search_1c_help_keyword` |
| Skipping `did_change_watched_files` | Call after batch edits so LSP stays in sync |

## Additional Reference

See [reference.md](reference.md) for URI mapping details and more examples.
