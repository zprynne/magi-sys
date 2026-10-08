# Shortcuts for macOS/Linux. Every target runs tasks.py, which also works on
# Windows: `uv run tasks.py <command>` (see `uv run tasks.py --help`).
#
#   make dev-mock PORT=8765    # override the API port (default 8000)

PORT ?= 8000
TASKS := uv run tasks.py

.PHONY: install dev dev-mock dev-mlx backend mock local mlx frontend build serve \
        schema types traces resources test lint typecheck check

install:   ; $(TASKS) install

# --- Run (API + frontend together; Ctrl-C stops both) ----------------------
dev:       ; $(TASKS) dev --port $(PORT)
dev-mock:  ; $(TASKS) dev --mock --port $(PORT)
dev-mlx:   ; $(TASKS) dev --models models/mlx.yaml --start-mlx --port $(PORT)

# --- Run pieces separately -------------------------------------------------
backend:   ; $(TASKS) api --reload --port $(PORT)
mock:      ; $(TASKS) api --mock --reload --port $(PORT)
local:     ; $(TASKS) api --models models/mlx.yaml --reload --port $(PORT)
mlx:       ; $(TASKS) mlx
frontend:  ; $(TASKS) frontend --port $(PORT)
build:     ; $(TASKS) build
serve:     ; $(TASKS) serve --port $(PORT)

# --- Contract and data -----------------------------------------------------
schema:    ; $(TASKS) schema
types:     ; $(TASKS) types
traces:    ; $(TASKS) traces
resources: ; $(TASKS) resources --models models/mlx.yaml

# --- Quality ---------------------------------------------------------------
test:      ; $(TASKS) test
lint:      ; $(TASKS) lint
typecheck: ; $(TASKS) typecheck
check:     ; $(TASKS) check
