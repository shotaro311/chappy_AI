VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: setup lint format test run sync-config

setup:
	python -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

lint:
	$(PYTHON) -m ruff check src tests

format:
	$(PYTHON) -m ruff format src tests

test:
	$(PYTHON) -m pytest -m "not slow"

run:
	PYTHONPATH=src $(PYTHON) -m src.main --config config/pc.dev.yaml

sync-config:
	rsync -av src/ pi:/opt/chappy_ai/src
