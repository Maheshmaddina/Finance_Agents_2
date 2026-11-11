"""
llm.py: connect the Agents SDK to the chosen LLM provider (config.PROVIDER).

Gemini, Groq and OpenRouter all expose an OpenAI-compatible Chat Completions
endpoint, so we just point an AsyncOpenAI client at their base_url and tell
the SDK to use Chat Completions. A small throttle spaces out requests so free
tier rate limits (requests per minute) are not hit; retries handle the rest.
"""

from __future__ import annotations

import asyncio
import os
import time

try:  # newer openai releases ship httpx2, older ones httpx
    import httpx2 as httpx
except ImportError:  # pragma: no cover
    import httpx
from agents import (Model, OpenAIChatCompletionsModel, set_default_openai_api,
                    set_default_openai_client, set_tracing_disabled)
from openai import AsyncOpenAI

from . import config

_lock = asyncio.Lock()
_last_request = 0.0
_client: AsyncOpenAI | None = None


async def _throttle(request: httpx.Request) -> None:
    """Wait so that requests are at least MIN_INTERVAL_S apart."""
    global _last_request
    if config.MIN_INTERVAL_S <= 0:
        return
    async with _lock:
        wait = _last_request + config.MIN_INTERVAL_S - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        _last_request = time.monotonic()


def api_key() -> str | None:
    return os.getenv(config.PROVIDER_CFG["key_env"])


def setup_llm() -> None:
    """Call once before running any agent."""
    key = api_key()
    if not key:
        raise RuntimeError(
            f"{config.PROVIDER_CFG['key_env']} is not set (LLM_PROVIDER={config.PROVIDER}). "
            "Copy .env.example to .env and add your key."
        )
    global _client
    client = _client = AsyncOpenAI(
        api_key=key,
        base_url=config.PROVIDER_CFG["base_url"],
        max_retries=8,  # back off and retry on 429 rate-limit errors
        timeout=120,
        http_client=httpx.AsyncClient(event_hooks={"request": [_throttle]}, timeout=120),
    )
    set_default_openai_client(client, use_for_tracing=False)
    if config.PROVIDER != "openai":
        set_default_openai_api("chat_completions")
        # SDK traces upload to OpenAI's dashboard, which needs an OpenAI key.
        set_tracing_disabled(True)


def resolve_model(name: str) -> str | Model:
    """Model to hand to Agent(model=...). For non-OpenAI providers we pass a
    model object, because the SDK would otherwise read a name like
    "openai/gpt-oss-120b" as a provider prefix and strip it."""
    if config.PROVIDER == "openai" or _client is None:
        return name
    return OpenAIChatCompletionsModel(model=name, openai_client=_client)


def parallel_setting() -> bool | None:
    """parallel_tool_calls value for ModelSettings (None = don't send it)."""
    return True if config.PROVIDER_CFG["parallel_param"] else None
