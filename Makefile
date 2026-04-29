.PHONY: install test lint alembic-heads run docker-build docker-up docker-down docker-logs docker-migrate docker-create-admin-help

install:
	python -m pip install --upgrade pip
	python -m pip install -e ".[dev]"

test:
	python -m pytest tests/unit

lint:
	python -m ruff check app tests

alembic-heads:
	alembic heads

run:
	uvicorn --app-dir app slaif_gateway.main:app --reload

docker-build:
	docker compose build

docker-up:
	docker compose up --build

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

docker-migrate:
	docker compose run --rm api slaif-gateway db upgrade

docker-create-admin-help:
	docker compose run --rm api slaif-gateway admin create --help
