.PHONY: install dev api db-up db-down migrate revision lint format typecheck test check docker-build helm-lint lab lab-down clean

install:            ## Install dependencies (incl. dev tools)
	uv sync

dev: db-up migrate api ## Start database, migrate, and run the API

api:                ## Run the API server with auto-reload
	uv run uvicorn opsmemory.api.app:create_app --factory --reload

db-up:              ## Start PostgreSQL (pgvector) via Docker Compose
	docker compose up -d postgres

db-down:            ## Stop and remove local services
	docker compose down

migrate:            ## Apply database migrations
	uv run alembic upgrade head

revision:           ## Autogenerate a migration: make revision m="message"
	uv run alembic revision --autogenerate -m "$(m)"

lint:               ## Run ruff checks
	uv run ruff check src tests migrations
	uv run ruff format --check src tests migrations

format:             ## Auto-format and fix lint issues
	uv run ruff format src tests migrations
	uv run ruff check --fix src tests migrations

typecheck:          ## Run mypy
	uv run mypy src

test:               ## Run the test suite
	uv run pytest

check: lint typecheck test helm-lint ## Run every quality gate (excl. docker build)

docker-build:       ## Build the container image
	docker build -t opsmemory:dev .

helm-lint:          ## Lint the Helm chart
	helm lint deploy/helm/opsmemory

lab:                ## One command: Kind cluster + Postgres + OpsMemory + sample knowledge
	./scripts/bootstrap-kind.sh

lab-down:           ## Tear down the Kind lab cluster
	kind delete cluster --name opsmemory-lab

clean:              ## Remove caches and build artifacts
	rm -rf .mypy_cache .ruff_cache .pytest_cache .coverage htmlcov dist build
