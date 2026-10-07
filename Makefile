.PHONY: install dev backend frontend mock schema types test lint typecheck check

install:
	cd backend && uv sync
	cd frontend && npm install

backend:
	cd backend && uv run magi-server --reload

mock:
	cd backend && MAGI_MOCK=1 uv run magi-server --reload

frontend:
	cd frontend && npm run dev

# Regenerate the JSON Schema from the pydantic models, then the TS types from it
schema:
	cd backend && uv run magi-schema

types: schema
	cd frontend && npm run gen:types

test:
	cd backend && uv run pytest

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && npm run lint

typecheck:
	cd backend && uv run mypy
	cd frontend && npm run typecheck

check: lint typecheck test
	cd backend && uv run magi-schema --check
