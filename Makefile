.PHONY: help setup test live check lint format

help: ## Show this help
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

setup: ## Create the venv and install runtime + dev deps
	uv venv --python 3.13
	uv pip install -e '.[dev]'

test: ## Run the test suite
	uv run pytest -q

live: ## Run the live stage exercises (dispatches a model; costs money)
	RUBRICA_LIVE=1 uv run pytest -m live -q

check: ## Lint and verify formatting, making no changes
	uv run ruff check .
	uv run ruff format --check .

lint: ## Auto-fix lint findings
	uv run ruff check --fix .

format: ## Reformat the code
	uv run ruff format .
