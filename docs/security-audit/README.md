# Аудит безопасности 1C Help MCP

Артефакты аудита безопасности проекта onec_help.

## Содержимое

| Файл | Описание |
|------|----------|
| [nda-checklist.md](nda-checklist.md) | Чеклист NDA при работе с конфиденциальным кодом |
| [nda-executor-template.md](nda-executor-template.md) | Шаблон соглашения о неразглашении для исполнителя аудита |
| [findings-report.md](findings-report.md) | Отчёт о находках (pip-audit, bandit, ручной анализ) |
| [recommendations-backlog.md](recommendations-backlog.md) | Приоритизированный backlog исправлений |

## План аудита

Полный план аудита — `.cursor/plans/security_audit_plan_*.plan.md` (или `docs/security-audit-prompt.md` как исходный промпт).

## Запуск сканов

```bash
# Зависимости
pip-audit

# SAST
bandit -r src/onec_help

# Docker (если установлены)
trivy image python:3.14-slim
hadolint Dockerfile
```
