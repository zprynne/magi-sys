.PHONY: install backend mock local mlx resources frontend build serve schema types traces test lint typecheck check

install:
	cd backend && uv sync --extra mlx
	cd frontend && npm install

# --- Run -------------------------------------------------------------------

backend:            ## API on :8000 against the real model (needs ANTHROPIC_API_KEY)
	cd backend && uv run magi-server --reload

mock:               ## API on :8000 replaying saved traces, no API calls
	cd backend && MAGI_MOCK=1 uv run magi-server --reload

mlx:                ## Start the local mlx_lm model servers for models/mlx.yaml
	cd backend && uv run --extra mlx magi-mlx --models ../models/mlx.yaml

local:              ## API on :8000 using the all-local MLX council (run `make mlx` first)
	cd backend && MAGI_MODELS=models/mlx.yaml uv run magi-server --reload

resources:          ## Disk and memory report (models, venv, running servers)
	cd backend && uv run --extra mlx magi-resources --models ../models/mlx.yaml

frontend:           ## Vite dev server on :5173 (proxies /api to :8000)
	cd frontend && npm run dev

build:
	cd frontend && npm run build

serve: build        ## Single process: the API also serves frontend/dist
	cd backend && uv run magi-server

# --- Contract --------------------------------------------------------------

schema:             ## pydantic models -> schema/magi-events.schema.json
	cd backend && uv run magi-schema

types: schema       ## JSON Schema -> frontend/src/types/events.generated.ts
	cd frontend && npm run gen:types

traces:             ## Rebuild the bundled example traces
	cd backend && uv run python scripts/build_example_traces.py

# --- Quality ---------------------------------------------------------------

test:
	cd backend && uv run pytest
	cd frontend && npm test

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && npm run lint

typecheck:
	cd backend && uv run mypy
	cd frontend && npm run typecheck

check: lint typecheck test
	cd backend && uv run magi-schema --check
	cd frontend && npm run check:types
