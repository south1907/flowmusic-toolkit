.PHONY: install install-dev run test lint format check

install:
	python3 -m venv .venv
	.venv/bin/python -m pip install --upgrade pip
	.venv/bin/python -m pip install .

install-dev:
	python3 -m venv .venv
	.venv/bin/python -m pip install --upgrade pip
	.venv/bin/python -m pip install -e ".[dev]"

run:
	.venv/bin/google-flow-music

test:
	.venv/bin/python -m pytest

lint:
	.venv/bin/ruff check app tests
	node --check extension/background.js
	node --check extension/popup.js
	python3 -m json.tool extension/manifest.json >/dev/null

format:
	.venv/bin/ruff format app tests
	.venv/bin/ruff check --fix app tests

check: lint test
