# 1C Help MCP — Docker commands
# Usage: make parse-fastcode | make load-snippets | make snippets
# Extra args: make parse-fastcode ARGS="--pages 1-5 --no-fetch-detail"

ARGS ?=

.PHONY: build parse-fastcode load-snippets load-snippets-from-project load-standards snippets up down bsl-start bsl-stop ingest build-index index-status help

# Rebuild mcp image (required after adding new commands like parse-fastcode)
build:
	docker compose build mcp

# Parse FastCode.im templates → snippets/fastcode_snippets.json
parse-fastcode:
	docker compose run --rm mcp python -m onec_help parse-fastcode $(ARGS)

# Load snippets from SNIPPETS_DIR into onec_help_memory (embeddings)
load-snippets:
	docker compose run --rm mcp python -m onec_help load-snippets $(ARGS)

# Load snippets from 1C project (mounts project, then --from-project)
# ARGS: extra args, e.g. ARGS="--per-function". PROJECT_PATH: host path (default: $(CURDIR))
load-snippets-from-project:
	docker compose run --rm -v "$${PROJECT_PATH:=$(CURDIR)}:/project:ro" mcp python -m onec_help load-snippets --from-project /project $(ARGS)

# Load v8-code-style docs into onec_help_memory (domain=standards).
# По умолчанию STANDARDS_REPO — авто-скачивание, temp удаляется после загрузки.
# Либо STANDARDS_DIR=/data/standards + volume, либо ARGS=path.
load-standards:
	docker compose run --rm mcp python -m onec_help load-standards $(ARGS)

# Parse FastCode + load snippets (full pipeline)
snippets: parse-fastcode load-snippets

# Ingest .hbk from HELP_SOURCE_BASE (/opt/1cv8): unpack, index, cleanup
ingest:
	docker compose exec mcp python -m onec_help ingest $(ARGS)

# Build index from directory with .md (path required: ARGS=/path/to/docs)
build-index:
	docker compose exec mcp python -m onec_help build-index $(ARGS)

# Show index status (topics, embeddings, DB size, ingest progress)
index-status:
	docker compose exec mcp python -m onec_help index-status

# Start services (qdrant + mcp + bsl-bridge)
up:
	BSL_HOST_PROJECTS_ROOT="$$(pwd)" docker compose up -d

# Stop services
down:
	docker compose down

# Start only BSL LS bridge
bsl-start:
	BSL_HOST_PROJECTS_ROOT="$$(pwd)" docker compose up -d bsl-bridge

# Stop only BSL LS bridge
bsl-stop:
	docker compose stop bsl-bridge

help:
	@echo "1C Help MCP — Docker targets"
	@echo ""
	@echo "  make build            Rebuild mcp image (after git pull / new commands)"
	@echo "  make parse-fastcode   Parse FastCode.im → fastcode_snippets.json"
	@echo "  make load-snippets             Load snippets from SNIPPETS_DIR"
	@echo "  make load-snippets-from-project  Load snippets from 1C project (mounts .)"
	@echo "  make load-standards   Load v8-code-style docs (STANDARDS_REPO auto or STANDARDS_DIR/ARGS)"
	@echo "  make snippets         parse-fastcode + load-snippets"
	@echo "  make ingest           Индексация .hbk из HELP_SOURCE_BASE (/opt/1cv8)"
	@echo "  make build-index      Индексация из папки с .md (ARGS=путь)"
	@echo "  make index-status     Статус индекса (топики, embeddings, размер БД)"
	@echo "  make up               Start qdrant + mcp + bsl-bridge"
	@echo "  make down             Stop all services"
	@echo "  make bsl-start        Start only BSL LS bridge"
	@echo "  make bsl-stop         Stop only BSL LS bridge"
	@echo ""
	@echo "Args via ARGS= (not --key=value):"
	@echo "  make parse-fastcode ARGS='--pages 1-51'"
	@echo "  make parse-fastcode ARGS='--pages 1-5 --no-fetch-detail'"
	@echo "  make load-snippets                      # from SNIPPETS_DIR"
	@echo "  make load-snippets-from-project         # from project root"
	@echo "  make load-snippets-from-project ARGS='--per-function'"
	@echo "  make load-snippets-from-project PROJECT_PATH=/path/to/1c"
	@echo "  make load-standards              # STANDARDS_REPO (default) or STANDARDS_DIR"
	@echo "  make load-standards ARGS='/path' # explicit path"
	@echo "  make ingest ARGS='--dry-run'"
	@echo "  make build-index ARGS='/data/docs_md'"
