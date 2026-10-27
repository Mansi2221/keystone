.PHONY: up down seed test eval eval-fast demo lint typecheck clean doctor smoke

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

smoke:
	uv run python scripts/smoke_test.py

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

doctor:
	@echo "=== Keystone Doctor ==="
	@echo ""
	@echo "--- Prerequisites ---"
	@printf "  Docker:          "; docker --version 2>/dev/null && true || (echo "MISSING — brew install --cask docker-desktop" && false)
	@printf "  Docker running:  "; docker info >/dev/null 2>&1 && echo "OK" || (echo "NOT RUNNING — open /Applications/Docker.app" && false)
	@printf "  uv:              "; (uv --version 2>/dev/null || $$HOME/.local/bin/uv --version 2>/dev/null) && true || (echo "MISSING — curl -LsSf https://astral.sh/uv/install.sh | sh" && false)
	@printf "  Python venv:     "; .venv/bin/python --version 2>/dev/null || (echo "MISSING — run: uv sync --extra dev" && false)
	@echo ""
	@echo "--- Environment ---"
	@printf "  .env file:       "; test -f .env && echo "OK" || (echo "MISSING — cp .env.example .env" && false)
	@printf "  Gemini key:      "; grep -qE "^GEMINI_API_KEY=.{10,}" .env 2>/dev/null && echo "SET" || echo "NOT SET (edit .env)"
	@printf "  Groq key:        "; grep -qE "^GROQ_API_KEY=.{10,}" .env 2>/dev/null && echo "SET" || echo "NOT SET (edit .env)"
	@printf "  OpenAI key:      "; grep -qE "^OPENAI_API_KEY=.{10,}" .env 2>/dev/null && ! grep -q "sk-your-key-here" .env 2>/dev/null && echo "SET" || echo "NOT SET (edit .env)"
	@printf "  Anthropic key:   "; grep -qE "^ANTHROPIC_API_KEY=.{10,}" .env 2>/dev/null && ! grep -q "sk-ant-your-key-here" .env 2>/dev/null && echo "SET" || echo "NOT SET (edit .env)"
	@printf "  Ollama:          "; curl -sf http://localhost:11434/api/tags >/dev/null 2>&1 && echo "RUNNING" || echo "NOT RUNNING (ollama serve)"
	@echo ""
	@echo "--- Services ---"
	@printf "  Postgres:        "; docker compose ps postgres 2>/dev/null | grep -q "healthy" && echo "HEALTHY" || echo "DOWN — docker compose up -d postgres"
	@printf "  Cerbos:          "; docker compose ps cerbos 2>/dev/null | grep -q "Up" && echo "UP" || echo "DOWN — docker compose up -d cerbos"
	@printf "  Langfuse:        "; docker compose ps langfuse 2>/dev/null | grep -q "Up" && echo "UP" || echo "DOWN — docker compose up -d langfuse"
	@echo ""
	@echo "--- Database ---"
	@printf "  Tables seeded:   "; docker exec keystone-postgres-1 psql -U keystone -d keystone -tAc "SELECT count(*) FROM employees" 2>/dev/null | grep -q "^[1-9]" && echo "YES ($$(docker exec keystone-postgres-1 psql -U keystone -d keystone -tAc 'SELECT count(*) FROM employees') employees)" || echo "NO — run: make seed"
	@printf "  RLS policies:    "; docker exec keystone-postgres-1 psql -U keystone -d keystone -tAc "SELECT count(*) FROM pg_policies WHERE schemaname='public'" 2>/dev/null | grep -q "^[1-9]" && echo "YES ($$(docker exec keystone-postgres-1 psql -U keystone -d keystone -tAc "SELECT count(*) FROM pg_policies WHERE schemaname='public'") policies)" || echo "NO — run: make seed"
	@printf "  Canaries:        "; docker exec keystone-postgres-1 psql -U keystone -d keystone -tAc "SELECT count(*) FROM canary_registry" 2>/dev/null | grep -q "^[1-9]" && echo "YES ($$(docker exec keystone-postgres-1 psql -U keystone -d keystone -tAc 'SELECT count(*) FROM canary_registry') canaries)" || echo "NO — run: make seed"
	@echo ""
	@echo "--- Ports ---"
	@printf "  5433 (Postgres): "; lsof -i :5433 >/dev/null 2>&1 && echo "IN USE" || echo "FREE"
	@printf "  3592 (Cerbos):   "; lsof -i :3592 >/dev/null 2>&1 && echo "IN USE" || echo "FREE"
	@printf "  3001 (Langfuse): "; lsof -i :3001 >/dev/null 2>&1 && echo "IN USE" || echo "FREE"
	@printf "  8000 (API):      "; lsof -i :8000 >/dev/null 2>&1 && echo "IN USE" || echo "FREE"
	@printf "  8501 (UI):       "; lsof -i :8501 >/dev/null 2>&1 && echo "IN USE" || echo "FREE"
	@echo ""
	@echo "=== Done ==="
