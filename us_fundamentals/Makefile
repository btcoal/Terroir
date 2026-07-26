.PHONY: sync fmt lint typecheck test pipeline check

sync:
	uv sync

fmt:
	uv run ruff format src tests

lint:
	uv run ruff check src tests

typecheck:
	uv run mypy

test:
	uv run pytest

pipeline:
	uv run python -m us_fundamentals.jobs.minimal_pipeline

check: lint typecheck test pipeline
