"""Centralized LLM client factory with rate limiting, retry, and disk cache.

Supports OpenAI, Anthropic, Gemini, Groq (all via OpenAI-compatible endpoints),
and Ollama (local). Each component (agent, judge, seed) can use a different
provider/model via .env config. Profiles (local/free/paid) set defaults.
"""

import hashlib
import json
import logging
import re
import threading
import time
from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage

from company.config import settings

logger = logging.getLogger(__name__)


def _redact_secrets(text: str) -> str:
    """Remove API keys and auth tokens from error messages."""
    for key_val in (
        settings.gemini_api_key, settings.groq_api_key,
        settings.openai_api_key, settings.anthropic_api_key,
    ):
        if key_val and len(key_val) > 8:
            text = text.replace(key_val, "***REDACTED***")
    text = re.sub(r'(Bearer\s+)\S+', r'\1***REDACTED***', text)
    text = re.sub(r'(key=)\S+', r'\1***REDACTED***', text)
    return text


# OpenAI-compatible base URLs for remote providers
PROVIDER_BASE_URLS = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "groq": "https://api.groq.com/openai/v1",
}

# Free-tier rate limits per provider (requests per minute)
PROVIDER_RATE_LIMITS: dict[str, dict[str, int]] = {
    "gemini": {"rpm": 10},
    "groq": {"rpm": 30},
    "openai": {"rpm": 60},
    "anthropic": {"rpm": 50},
    "ollama": {"rpm": 999},  # Local — no limit
}

# Disk cache directory
CACHE_DIR = Path(".llm_cache")

# ── LLM call counter (for eval reporting) ────────────────────

_llm_call_count = 0
_llm_call_lock = threading.Lock()


def get_call_count() -> int:
    return _llm_call_count


def reset_call_count() -> None:
    global _llm_call_count
    with _llm_call_lock:
        _llm_call_count = 0


def _increment_call_count() -> None:
    global _llm_call_count
    with _llm_call_lock:
        _llm_call_count += 1


# ── Rate Limiter ──────────────────────────────────────────────


class RateLimiter:
    """Token-bucket rate limiter with per-provider RPM tracking."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._request_log: dict[str, list[float]] = {}

    def wait_if_needed(self, provider: str) -> None:
        """Block until the next request is allowed under RPM limits."""
        limits = PROVIDER_RATE_LIMITS.get(provider, {"rpm": 60})
        rpm = limits["rpm"]

        with self._lock:
            now = time.time()
            log = self._request_log.setdefault(provider, [])
            cutoff = now - 60
            log[:] = [t for t in log if t > cutoff]

            if len(log) >= rpm:
                wait_time = log[0] - cutoff + 0.1
                if wait_time > 0:
                    logger.info(
                        "Rate limit: waiting %.1fs for %s (%d/%d RPM)",
                        wait_time, provider, len(log), rpm,
                    )
                    self._lock.release()
                    try:
                        time.sleep(wait_time)
                    finally:
                        self._lock.acquire()
                    now = time.time()
                    cutoff = now - 60
                    log[:] = [t for t in log if t > cutoff]

            log.append(time.time())


_rate_limiter = RateLimiter()


# ── Disk Cache ────────────────────────────────────────────────


def _cache_key(provider: str, model: str, messages: list[BaseMessage], principal_id: int | None = None) -> str:
    parts = [provider, model]
    for m in messages:
        parts.append(f"{m.type}:{m.content}")
    if principal_id is not None:
        parts.append(f"principal:{principal_id}")
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def _cache_get(key: str) -> str | None:
    path = CACHE_DIR / f"{key}.json"
    if path.exists():
        try:
            return json.loads(path.read_text()).get("content")
        except (json.JSONDecodeError, OSError):
            return None
    return None


def _cache_set(key: str, content: str, provider: str, model: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{key}.json"
    try:
        path.write_text(json.dumps({
            "provider": provider, "model": model,
            "content": content, "cached_at": time.time(),
        }))
    except OSError:
        pass


# ── Retry with Backoff ───────────────────────────────────────


def _invoke_with_retry(
    llm: BaseChatModel,
    messages: list[BaseMessage],
    provider: str,
    max_retries: int = 4,
) -> AIMessage:
    """Invoke LLM with exponential backoff on 429 / rate-limit errors."""
    for attempt in range(max_retries + 1):
        _rate_limiter.wait_if_needed(provider)
        try:
            result = llm.invoke(messages)
            _increment_call_count()
            return result
        except Exception as e:
            err_str = str(e).lower()
            is_rate_limit = "429" in err_str or "rate" in err_str or "quota" in err_str or "resource_exhausted" in err_str

            # Don't retry daily quota exhaustion
            is_daily_quota = "per day" in err_str or "per_day" in err_str
            if is_daily_quota:
                logger.error("Daily quota exhausted for %s — not retrying: %s", provider, _redact_secrets(str(e)))
                raise

            if is_rate_limit and attempt < max_retries:
                wait = (2 ** attempt) * 2
                logger.warning(
                    "Rate limited by %s (attempt %d/%d), waiting %ds",
                    provider, attempt + 1, max_retries, wait,
                )
                time.sleep(wait)
            else:
                raise


# ── Provider / Model Resolution ──────────────────────────────


def _resolve_provider_model(purpose: str) -> tuple[str, str]:
    """Resolve provider and model for a given purpose.

    Priority: explicit env var > profile default.
    """
    if purpose == "judge":
        provider = settings.effective_judge_provider()
        model = settings.effective_judge_model()
    elif purpose == "seed":
        provider = settings.seed_provider or settings.effective_llm_provider()
        model = settings.seed_model or settings.effective_llm_model()
    else:  # "agent"
        provider = settings.effective_llm_provider()
        model = settings.effective_llm_model()
    return provider, model


def _get_api_key(provider: str) -> str:
    keys = {
        "openai": settings.openai_api_key,
        "anthropic": settings.anthropic_api_key,
        "gemini": settings.gemini_api_key,
        "groq": settings.groq_api_key,
        "ollama": "ollama",  # Ollama needs no real key
    }
    return keys.get(provider, "")


def active_profile_info() -> dict[str, str]:
    """Return a dict describing the active profile and effective providers."""
    agent_p, agent_m = _resolve_provider_model("agent")
    judge_p, judge_m = _resolve_provider_model("judge")
    return {
        "profile": settings.profile,
        "agent": f"{agent_p}/{agent_m}",
        "judge": f"{judge_p}/{judge_m}",
    }


# ── Public API ────────────────────────────────────────────────


def get_llm(purpose: str = "agent") -> BaseChatModel:
    """Create a raw LLM client for the given purpose."""
    provider, model = _resolve_provider_model(purpose)
    api_key = _get_api_key(provider)

    logger.debug("LLM [%s]: provider=%s model=%s", purpose, provider, model)

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model, temperature=0, api_key=api_key or None)

    if provider == "ollama":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model, temperature=0,
            base_url=settings.ollama_base_url,
            api_key="ollama",  # Ollama ignores this but langchain requires it
        )

    if provider in ("gemini", "groq"):
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model, temperature=0,
            base_url=PROVIDER_BASE_URLS[provider],
            api_key=api_key or "missing-key",
        )

    # Default: OpenAI
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=model, temperature=0, api_key=api_key or None)


def invoke_llm(
    messages: list[BaseMessage],
    purpose: str = "agent",
    principal_id: int | None = None,
    use_cache: bool = True,
) -> AIMessage:
    """Invoke an LLM with rate limiting, retry, and disk cache."""
    provider, model = _resolve_provider_model(purpose)

    if use_cache:
        key = _cache_key(provider, model, messages, principal_id)
        cached = _cache_get(key)
        if cached is not None:
            logger.debug("Cache hit for %s/%s", provider, model)
            return AIMessage(content=cached)

    llm = get_llm(purpose)
    response = _invoke_with_retry(llm, messages, provider)

    if use_cache:
        _cache_set(key, response.content, provider, model)

    return response


def verify_key(purpose: str = "agent") -> tuple[bool, str]:
    """Verify that the configured provider works with a minimal call."""
    provider, model = _resolve_provider_model(purpose)
    api_key = _get_api_key(provider)

    if provider != "ollama" and not api_key:
        return False, f"No API key set for {provider}. Set {provider.upper()}_API_KEY in .env"

    try:
        from langchain_core.messages import HumanMessage
        llm = get_llm(purpose)
        _rate_limiter.wait_if_needed(provider)
        response = llm.invoke([HumanMessage(content="Say 'ok' and nothing else.")])
        _increment_call_count()
        return True, f"{provider}/{model}: {response.content.strip()[:50]}"
    except Exception as e:
        return False, f"{provider}/{model} failed: {_redact_secrets(str(e))}"
