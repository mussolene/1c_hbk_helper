# 1C Help MCP — Docker commands
# Usage: make parse-fastcode | make load-snippets | make snippets
# Extra args: make parse-fastcode ARGS="--pages 1-5 --no-fetch-detail"
# Split mode: make up-split | make ingest-split | make build-split

ARGS ?=
# Для unpack-help: исходники справки на хосте, выходная папка, языки
HELP_SOURCE_PATH ?= /opt/1cv8
UNPACK_OUTPUT ?= data/unpacked
HELP_LANGS ?= ru

COMPOSE = docker compose
COMPOSE_SPLIT = docker compose -f docker-compose.split.yml

.PHONY: build build-split parse-fastcode load-snippets load-snippets-from-project load-standards snippets
.PHONY: up down up-split down-split bsl-start bsl-stop
.PHONY: ingest ingest-split build-index build-index-split index-status index-status-split
.PHONY: unpack-help help

# Rebuild mcp image (required after adding new commands like parse-fastcode)
build:
	$(COMPOSE) build mcp

# Rebuild mcp/ingest-worker (split). SERVICE=mcp|ingest-worker — только один
build-split:
	$(COMPOSE_SPLIT) up -d --build $(if $(SERVICE),$(SERVICE),mcp ingest-worker)

# Parse FastCode.im templates → snippets/fastcode_snippets.json
parse-fastcode:
	$(COMPOSE) run --rm mcp python -m onec_help parse-fastcode $(ARGS)

# Load snippets from SNIPPETS_DIR into onec_help_memory (embeddings)
load-snippets:
	$(COMPOSE) run --rm mcp python -m onec_help load-snippets $(ARGS)

# Load snippets from 1C project (mounts project, then --from-project)
# ARGS: extra args, e.g. ARGS="--per-function". PROJECT_PATH: host path (default: $(CURDIR))
load-snippets-from-project:
	$(COMPOSE) run --rm -v "$${PROJECT_PATH:=$(CURDIR)}:/project:ro" mcp python -m onec_help load-snippets --from-project /project $(ARGS)

# Load standards into onec_help_memory (domain=standards).
# По умолчанию оба репо: v8-code-style и v8std. Либо STANDARDS_DIR, либо ARGS=path.
load-standards:
	$(COMPOSE) run --rm mcp python -m onec_help load-standards $(ARGS)

# Parse FastCode + load snippets (full pipeline)
snippets: parse-fastcode load-snippets

# Ingest .hbk from HELP_SOURCE_BASE (/opt/1cv8): unpack, index, cleanup
ingest:
	$(COMPOSE) exec mcp python -m onec_help ingest $(ARGS)

# Ingest (split mode) — выполняется в ingest-worker
ingest-split:
	$(COMPOSE_SPLIT) exec ingest-worker python -m onec_help ingest $(ARGS)

# Build index from directory with .md (path required: ARGS=/path/to/docs)
build-index:
	$(COMPOSE) exec mcp python -m onec_help build-index $(ARGS)

# Build index (split mode)
build-index-split:
	$(COMPOSE_SPLIT) exec mcp python -m onec_help build-index $(ARGS)

# Show index status (topics, embeddings, DB size, ingest progress)
index-status:
	$(COMPOSE) exec mcp python -m onec_help index-status

# Index status (split mode)
index-status-split:
	$(COMPOSE_SPLIT) exec mcp python -m onec_help index-status

# Выгрузка справки в папку: распаковка .hbk без индексации.
# HELP_SOURCE_PATH — каталог с версиями 1С (/opt/1cv8); UNPACK_OUTPUT — куда положить (data/unpacked)
unpack-help:
	mkdir -p "$(UNPACK_OUTPUT)"
	$(COMPOSE) run --rm -v "$(HELP_SOURCE_PATH):/input:ro" -v "$(abspath $(UNPACK_OUTPUT)):/output" mcp python -m onec_help unpack-dir /input -o /output -l $(HELP_LANGS) $(ARGS)

# Start services (qdrant + mcp + bsl-bridge)
up:
	BSL_HOST_PROJECTS_ROOT="$$(pwd)" $(COMPOSE) up -d

# Start split mode (mcp api-only + ingest-worker)
up-split:
	BSL_HOST_PROJECTS_ROOT="$$(pwd)" $(COMPOSE_SPLIT) up -d

# Start split + serve (нужен unpack-help или ./data/unpacked)
up-split-serve:
	BSL_HOST_PROJECTS_ROOT="$$(pwd)" $(COMPOSE_SPLIT) --profile serve up -d

# Stop services
down:
	$(COMPOSE) down

# Stop split mode
down-split:
	$(COMPOSE_SPLIT) down

# Start only BSL LS bridge
bsl-start:
	BSL_HOST_PROJECTS_ROOT="$$(pwd)" $(COMPOSE) up -d bsl-bridge

# Stop only BSL LS bridge
bsl-stop:
	$(COMPOSE) stop bsl-bridge

help:
	@echo "1C Help MCP — Docker targets"
	@echo ""
	@echo "  make build            Rebuild mcp image (after git pull / new commands)"
	@echo "  make build-split      Rebuild mcp+ingest-worker (split). SERVICE=mcp|ingest-worker — один"
	@echo "  make parse-fastcode   Parse FastCode.im → fastcode_snippets.json"
	@echo "  make load-snippets    Load snippets from SNIPPETS_DIR"
	@echo "  make load-snippets-from-project  Load snippets from 1C project (mounts .)"
	@echo "  make load-standards   Load standards (STANDARDS_REPOS — оба репо по умолчанию, или STANDARDS_DIR)"
	@echo "  make snippets         parse-fastcode + load-snippets"
	@echo "  make unpack-help      Выгрузка справки в папку (распаковка .hbk без индексации)"
	@echo "  make ingest           Индексация .hbk из HELP_SOURCE_BASE (/opt/1cv8)"
	@echo "  make ingest-split     Индексация (split mode, в ingest-worker)"
	@echo "  make build-index      Индексация из папки с .md (ARGS=путь)"
	@echo "  make index-status     Статус индекса (топики, embeddings, размер БД)"
	@echo "  make index-status-split  Статус индекса (split mode)"
	@echo "  make up               Start qdrant + mcp + bsl-bridge"
	@echo "  make up-split         Start split mode (mcp api-only + ingest-worker)"
	@echo "  make up-split-serve   Start split + serve (нужен unpack-help)"
	@echo "  make down             Stop all services"
	@echo "  make down-split       Stop split mode"
	@echo "  make bsl-start        Start only BSL LS bridge"
	@echo "  make bsl-stop         Stop only BSL LS bridge"
	@echo ""
	@echo "Args:"
	@echo "  make parse-fastcode ARGS='--pages 1-51'"
	@echo "  make load-snippets-from-project PROJECT_PATH=/path/to/1c"
	@echo "  make unpack-help HELP_SOURCE_PATH=/opt/1cv8 UNPACK_OUTPUT=data/unpacked HELP_LANGS=ru"
	@echo "  make ingest ARGS='--dry-run'"
	@echo "  make build-split SERVICE=mcp  # rebuild only mcp"
