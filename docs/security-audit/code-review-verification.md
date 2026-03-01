# Верификация код-ревью (аудит безопасности)

Проверка критических участков кода по плану аудита. Дата: 2026-03-01.

## Результаты

| Участок | Проверка | Статус |
|---------|----------|--------|
| `embedding.py` | `_is_safe_embedding_url` — только http/https | OK |
| `embedding.py` | `_mask_url_for_log` — URL не в логах полностью | OK |
| `entrypoint.sh` | EMBEDDING_API_KEY исключён из `.ingest_env` | OK |
| `web.py`, `cli.py` | `HELP_SERVE_ALLOWED_DIRS`, `_directory_allowed` до serve | OK |
| `form_metadata.py` | defusedxml при наличии (try/import) | OK |
| `memory.py` | Хранение JSONL/Qdrant, `path_inside_base` | OK |
| `standards_loader.py` | Валидация owner/repo, только https://github.com | OK |

## CI

- pip-audit, hadolint, trivy — в [.github/workflows/security.yml](../../.github/workflows/security.yml)
- pip обновляется до >=26 перед pip-audit (CVE-2026-1703)
