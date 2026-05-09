.PHONY: install lint format typecheck test up down migrate run-once clean

install:
	uv sync --extra dev

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

format:
	uv run ruff format src tests
	uv run ruff check --fix src tests

typecheck:
	uv run mypy src

test:
	uv run pytest tests/unit tests/contract

test-integration:
	uv run pytest tests/integration -m integration

up:
	docker compose up -d

down:
	docker compose down -v

migrate:
	docker compose run --rm migrate

run-once:
	docker compose exec app-worker cti run-once $(SOURCE)

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov build dist *.egg-info
	find . -name __pycache__ -prune -exec rm -rf {} +
