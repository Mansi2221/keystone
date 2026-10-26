.PHONY: up down seed test eval eval-fast demo lint typecheck clean

up:
	docker compose up -d --build

down:
	docker compose down

seed:
	uv run python -m company.seed

test:
	uv run pytest tests/ -v --tb=short

test-unit:
	uv run pytest tests/unit/ -v --tb=short -m unit

test-integration:
	uv run pytest tests/integration/ -v --tb=short -m integration

eval:
	uv run python -m evals.runner --suite all

eval-fast:
	uv run python -m evals.runner --suite all --fast

demo:
	uv run streamlit run ui/app.py

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

typecheck:
	uv run mypy company/ agent/ api/ --ignore-missing-imports

clean:
	docker compose down -v
	rm -rf .seed_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
