FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy project files
COPY pyproject.toml .
COPY company/ company/
COPY agent/ agent/
COPY api/ api/
COPY policy/ policy/
COPY mcp_servers/ mcp_servers/
COPY evals/ evals/

# Install dependencies
RUN uv sync --no-dev

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
