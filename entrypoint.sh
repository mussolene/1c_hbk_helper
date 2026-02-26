#!/bin/sh
# If running as root: fix volume ownership and run cron as app user, then drop to app for main process.
if [ "$(id -u)" = "0" ]; then
  [ -d /data ] && chown -R app:app /data 2>/dev/null || true
  env | grep -E '^(QDRANT_|HELP_|INGEST_|WATCHDOG_|MEMORY_|EMBEDDING_)' | sed 's/^/export /' > /app/.ingest_env 2>/dev/null || true
  chown app:app /app/.ingest_env 2>/dev/null || true
  if [ -d /opt/1cv8 ]; then
    crontab -u app /app/crontab 2>/dev/null || true
    cron
    ( gosu app sh -c '. /app/.ingest_env 2>/dev/null; cd /app && python -m onec_help ingest >> /app/var/log/ingest.log 2>&1' ) &
  fi
  if [ "$WATCHDOG_ENABLED" = "1" ]; then
    ( gosu app sh -c '. /app/.ingest_env 2>/dev/null; cd /app && python -m onec_help watchdog >> /app/var/log/watchdog.log 2>&1' ) &
  fi
  exec gosu app "$@"
fi
exec "$@"
