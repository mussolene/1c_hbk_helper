#!/bin/sh
# Если смонтирован /opt/1cv8 — сохраняем env для cron, запускаем cron (3:00) и один раз в фоне ingest при старте.
if [ -d /opt/1cv8 ]; then
  env | grep -E '^(QDRANT_|HELP_)' | sed 's/^/export /' > /app/.ingest_env 2>/dev/null || true
  crontab /app/crontab 2>/dev/null || true
  cron
  # Индексация в фоне при старте контейнера (логи в /var/log/ingest.log)
  ( . /app/.ingest_env 2>/dev/null; cd /app && python -m onec_help ingest >> /var/log/ingest.log 2>&1 ) &
fi
exec "$@"
