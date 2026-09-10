.PHONY: help setup test live check lint format release

help: ## Show this help
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

# `uv sync` creates the venv itself, so there is no separate `uv venv` step, and
# it installs from the committed uv.lock -- which is the point: CI resolves the
# same pins a contributor gets, so `ruff format --check` cannot go red on a
# version difference nobody chose. --python is explicit because there is no
# .python-version file; requires-python admits >=3.13 and dev pins 3.13.
setup: ## Create the venv and install runtime + dev deps from uv.lock
	uv sync --python 3.13 --extra dev

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

# The guard is a recipe line inside a parse-time conditional, so it fires only when
# this target is actually built -- `make test` with no VERSION set is unaffected.
# Without it, `make release` would run the script with an empty version, which the
# script rejects, but only after fetching the remote.
release: ## Cut a release: make release VERSION=0.2.0
ifndef VERSION
	$(error VERSION is required, e.g. make release VERSION=0.1.0)
endif
	./scripts/release.sh "$(VERSION)"
