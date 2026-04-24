.PHONY: install test lint run

install:
	python -m pip install --upgrade pip
	python -m pip install -e ".[dev]"

test:
	python -m pytest tests/unit

lint:
	python -m ruff check app tests

run:
	uvicorn --app-dir app slaif_gateway.main:app --reload
