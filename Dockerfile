# 1C Help: app container (Python + p7zip-full + cron для индексации по расписанию).
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    p7zip-full \
    cron \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml .
COPY src/ src/
COPY templates/ templates/
COPY entrypoint.sh crontab ./
RUN chmod +x /app/entrypoint.sh \
    && pip install --no-cache-dir -e .

ENV PORT=5000
EXPOSE 5000

# Default: run MCP over stdio; override with CMD serve /data or custom
ENV HELP_PATH=/data
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/ready')" || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "-m", "onec_help", "serve", "/data"]
