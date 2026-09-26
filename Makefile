SHELL := /bin/bash

PYTHONPATH := src
export PYTHONPATH

.PHONY: help setup lock lint format test normalize compact build score clean

help:
	@grep -E '^[a-zA-Z_-]+:' $(MAKEFILE_LIST) | cut -d: -f1 | sort -u

setup:
	uv python pin 3.12
	uv sync

lock:
	uv lock

lint:
	uv run --group lint ruff check src scripts tests
	uv run --group lint ruff format --check src scripts tests

format:
	uv run --group lint ruff format src scripts tests

test:
	uv run python -m unittest discover -s tests -t . -v

normalize:
	uv run python scripts/normalize_corpus.py

compact:
	uv run python scripts/compact_index.py

build:
	bash scripts/build_index.sh

score:
	uv run python -m hms.eval.score

clean:
	rm -rf .ruff_cache .pytest_cache
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
