# 1C Help MCP — Docker commands
# По умолчанию: split (mcp + ingest-worker). Для одного контейнера: make up-full, make ingest-full.
# Usage: make parse-fastcode | make load-snippets | make snippets
# Pages: auto by default. Limit: ARGS="--pages 1-5 --no-fetch-detail"

ARGS ?=
HELP_SOURCE_PATH ?= /opt/1cv8
UNPACK_OUTPUT ?= data/unpacked
HELP_LANGS ?= ru

COMPOSE = docker compose
COMPOSE_FULL = docker compose -f docker-compose.full.yml

# По умолчанию split; для full добавлять -full к таргету
INGEST_SERVICE = ingest-worker
INDEX_STATUS_SERVICE = mcp

.PHONY: build build-full parse-fastcode parse-helpf load-snippets load-snippets-from-project load-standards snippets
.PHONY: up down up-full down-full bsl-start bsl-stop
.PHONY: init init-full reinit reinit-full ingest ingest-full build-index build-index-full index-status index-status-full
.PHONY: watch-index-status watch-index-status-full unpack-help help

WATCH_INTERVAL ?= 2

# Сборка образов (split). SERVICE=mcp|ingest-worker — только один сервис
build:
	$(COMPOSE) build $(if $(SERVICE),$(SERVICE),mcp ingest-worker)

# Сборка образа (full, один контейнер mcp)
build-full:
	$(COMPOSE_FULL) build mcp

# Parse FastCode.im templates → snippets/fastcode_snippets.json
parse-fastcode:
	$(COMPOSE) run --rm mcp python -m onec_help parse-fastcode $(ARGS)

# Parse HelpF.pro FAQ/Files → snippets/helpf_snippets.json
parse-helpf:
	$(COMPOSE) run --rm mcp python -m onec_help parse-helpf $(ARGS)

# Load snippets from SNIPPETS_DIR into onec_help_memory
load-snippets:
	$(COMPOSE) run --rm mcp python -m onec_help load-snippets $(ARGS)

# Load snippets from 1C project
load-snippets-from-project:
	$(COMPOSE) run --rm -v "$${PROJECT_PATH:=$(CURDIR)}:/project:ro" mcp python -m onec_help load-snippets --from-project /project $(ARGS)

# Load standards into onec_help_memory
load-standards:
	$(COMPOSE) run --rm mcp python -m onec_help load-standards $(ARGS)

# Parse FastCode + load snippets
snippets: parse-fastcode load-snippets

# init: ingest + load-snippets + load-standards (no erase)
init:
	$(COMPOSE) exec $(INGEST_SERVICE) python -m onec_help init $(ARGS)

init-full:
	$(COMPOSE_FULL) exec mcp python -m onec_help init $(ARGS)

# reinit: erase collections + cache, then init
reinit:
	$(COMPOSE) exec $(INGEST_SERVICE) python -m onec_help reinit $(ARGS)

reinit-full:
	$(COMPOSE_FULL) exec mcp python -m onec_help reinit $(ARGS)

# Ingest .hbk (split, default) — в ingest-worker
ingest:
	$(COMPOSE) exec $(INGEST_SERVICE) python -m onec_help ingest $(ARGS)

# Ingest (full) — в mcp
ingest-full:
	$(COMPOSE_FULL) exec mcp python -m onec_help ingest $(ARGS)

# Build index from directory with .md
build-index:
	$(COMPOSE) exec $(INDEX_STATUS_SERVICE) python -m onec_help build-index $(ARGS)

build-index-full:
	$(COMPOSE_FULL) exec mcp python -m onec_help build-index $(ARGS)

# Index status
index-status:
	$(COMPOSE) exec $(INDEX_STATUS_SERVICE) python -m onec_help index-status

index-status-full:
	$(COMPOSE_FULL) exec mcp python -m onec_help index-status

# Watch index status
watch-index-status:
	$(COMPOSE) exec -it $(INDEX_STATUS_SERVICE) python -m onec_help index-status --watch --interval $(WATCH_INTERVAL)

watch-index-status-full:
	$(COMPOSE_FULL) exec -it mcp python -m onec_help index-status --watch --interval $(WATCH_INTERVAL)

# Unpack .hbk без индексации
unpack-help:
	mkdir -p "$(UNPACK_OUTPUT)"
	$(COMPOSE) run --rm -v "$(HELP_SOURCE_PATH):/input:ro" -v "$(abspath $(UNPACK_OUTPUT)):/output" mcp python -m onec_help unpack-dir /input -o /output -l $(HELP_LANGS) $(ARGS)

# Start (split: qdrant + mcp + ingest-worker + bsl-bridge)
up:
	BSL_HOST_PROJECTS_ROOT="$$(pwd)" $(COMPOSE) up -d

# Start full (один контейнер mcp)
up-full:
	BSL_HOST_PROJECTS_ROOT="$$(pwd)" $(COMPOSE_FULL) up -d

# Start split + serve
up-serve:
	BSL_HOST_PROJECTS_ROOT="$$(pwd)" $(COMPOSE) --profile serve up -d

# Stop
down:
	$(COMPOSE) down

down-full:
	$(COMPOSE_FULL) down

# BSL LS bridge only
bsl-start:
	BSL_HOST_PROJECTS_ROOT="$$(pwd)" $(COMPOSE) up -d bsl-bridge

bsl-stop:
	$(COMPOSE) stop bsl-bridge

help:
	@echo "1C Help MCP — Docker (по умолчанию split)"
	@echo ""
	@echo "  make build            Сборка образов mcp+ingest-worker (split). SERVICE=mcp|ingest-worker"
	@echo "  make build-full       Сборка образа mcp (full)"
	@echo "  make parse-fastcode   Parse FastCode.im → fastcode_snippets.json"
	@echo "  make parse-helpf      Parse HelpF.pro FAQ/Files → helpf_snippets.json"
	@echo "  make load-snippets    Load snippets from SNIPPETS_DIR"
	@echo "  make load-snippets-from-project  Load from 1C project"
	@echo "  make load-standards   Load standards (STANDARDS_REPOS)"
	@echo "  make snippets         parse-fastcode + load-snippets"
	@echo "  make init             ingest + load-snippets + load-standards (не стирает)"
	@echo "  make reinit           init (если индекс есть — без стирания). reinit ARGS='--force' — стереть и init"
	@echo "  make unpack-help      Распаковка .hbk без индексации"
	@echo "  make ingest           Индексация .hbk (split, ingest-worker)"
	@echo "  make ingest-full      Индексация (full, mcp)"
	@echo "  make build-index      Индексация из папки (ARGS=путь)"
	@echo "  make index-status     Статус индекса"
	@echo "  make watch-index-status  Статус в реальном времени"
	@echo "  make up               Start split (qdrant + mcp + ingest-worker)"
	@echo "  make up-full          Start full (один контейнер mcp)"
	@echo "  make up-serve         Start split + serve"
	@echo "  make down             Stop"
	@echo ""
	@echo "Args: ARGS=...  make ingest ARGS='--dry-run'"
