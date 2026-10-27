# Running Keystone End-to-End

## Prerequisites

| Tool | Required | Check | Install |
|------|----------|-------|---------|
| Docker Desktop | Yes | `docker --version` | `brew install --cask docker-desktop` |
| uv | Yes | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Python 3.12+ | Yes | Managed by uv | `uv python install 3.12` |
| LLM API key | Yes (for agent/eval) | — | See LLM Providers below |

Run `make doctor` to check everything at once.

## Setup

### 1. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set your LLM provider and API key.

### 2. LLM Providers

Keystone supports four LLM providers. **Gemini is the default** (generous free tier).

| Provider | Default model | Free-tier limits | Env var |
|----------|---------------|------------------|---------|
| **Gemini** | `gemini-3.5-flash` | 10 RPM, 250k TPM | `GEMINI_API_KEY` |
| **Groq** | `llama-3.1-8b-instant` | ~30 RPM, ~15k TPM | `GROQ_API_KEY` |
| OpenAI | `gpt-4o-mini` | Paid only | `OPENAI_API_KEY` |
| Anthropic | `claude-sonnet-4-20250514` | Paid only | `ANTHROPIC_API_KEY` |

**Quickstart with Gemini (free):**

```
LLM_PROVIDER=gemini
LLM_MODEL=gemini-3.5-flash
GEMINI_API_KEY=your-key-from-aistudio.google.com
```

**Quickstart with Groq (free):**

```
LLM_PROVIDER=groq
LLM_MODEL=llama-3.1-8b-instant
GROQ_API_KEY=your-key-from-console.groq.com
```

**Per-component overrides** (optional): You can use different providers for the agent, eval judge, and seed generator:

```
# Agent uses Gemini
LLM_PROVIDER=gemini
LLM_MODEL=gemini-3.5-flash

# Eval judge uses Groq (faster for scoring)
JUDGE_PROVIDER=groq
JUDGE_MODEL=llama-3.1-8b-instant

# Seed generator (future) uses Gemini
SEED_PROVIDER=gemini
SEED_MODEL=gemini-3.5-flash
```

### 3. Start infrastructure

```bash
docker compose up -d postgres cerbos langfuse
```

This starts:
- **Postgres 16** with pgvector on port 5433 (mapped to avoid conflicts with local Postgres)
- **Cerbos** policy engine on ports 3592 (HTTP) / 3593 (gRPC)
- **Langfuse** tracing on port 3001

Wait for Postgres to be healthy:

```bash
docker compose ps   # postgres should show (healthy)
```

### 4. Install Python dependencies

```bash
uv sync --extra dev
```

### 5. Seed the database

```bash
make seed
```

This creates:
- 116 employees across 5 departments
- 168 salary records, 218 reviews, 301 leave records, 3 terminations
- 2,000 tickets with 5,081 comments
- 300 documents (16 with prompt injections, 20 duplicates, 15 stale)
- 42 chat channels with 5,000 messages
- 80 customers with 150 deals
- 1,157 canary strings for leak detection
- 23 RLS policies on 11 tables

### 6. Run tests

```bash
make test          # All tests (unit + integration)
make test-unit     # Unit tests only (no DB required)
make test-integration  # Integration tests (requires seeded DB)
```

### 7. Smoke test (verify LLM connection)

```bash
make smoke         # Verifies key, then runs 3 questions x 4 users
```

### 8. Run the API

```bash
uv run uvicorn api.main:app --host 0.0.0.0 --port 8000
```

### 9. Run evaluations

```bash
make eval          # Full suite (requires LLM API key)
make eval-fast     # Stratified 20% subset for CI
```

### 10. Launch the demo UI

```bash
make demo          # Starts Streamlit on port 8501
```

## Rate Limiting and Caching

Keystone includes built-in protections for free-tier API usage:

- **Client-side rate limiter**: Enforces per-provider RPM limits (e.g., 10 RPM for Gemini free tier). Automatically waits when approaching the limit.
- **Exponential backoff**: On 429 (rate limit) errors, retries with 2/4/8/16 second delays.
- **Disk cache**: LLM responses are cached in `.llm_cache/` keyed on provider + model + prompt + principal. Reruns cost nothing. Delete `.llm_cache/` to clear.

## Ports

| Service | Port |
|---------|------|
| Postgres | 5433 |
| Cerbos HTTP | 3592 |
| Cerbos gRPC | 3593 |
| Langfuse | 3001 |
| API | 8000 |
| Streamlit UI | 8501 |

## Troubleshooting

**Port 5432 conflict**: The compose file maps Postgres to 5433 to avoid conflicts with a local Postgres installation. If 5433 is also taken, edit `POSTGRES_PORT` in `.env`.

**RLS not enforced**: The seed script applies RLS policies automatically. If tests show no filtering, re-run `make seed`.

**Docker not in PATH**: Docker Desktop installs binaries to `~/.docker/bin/`. Add to your shell profile:
```bash
export PATH="$HOME/.docker/bin:$PATH"
```

**Rate limit errors**: If you see 429 errors, the built-in rate limiter will retry automatically. For persistent issues, check your provider's free-tier quota at their dashboard.

**Teardown**: To remove all containers and data:
```bash
make clean    # Stops containers, removes volumes, clears seed cache
```
