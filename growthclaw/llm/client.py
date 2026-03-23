"""Unified LLM client with provider chain, usage tracking, and JSON parsing."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Protocol

from jinja2 import Environment, PackageLoader

logger = logging.getLogger("growthclaw.llm")

# Jinja2 template environment
_template_env = Environment(loader=PackageLoader("growthclaw", "prompts"))


def render_template(template_name: str, **kwargs: Any) -> str:
    """Render a Jinja2 prompt template."""
    template = _template_env.get_template(template_name)
    return template.render(**kwargs)


class LLMProvider(Protocol):
    """Protocol for LLM providers."""

    async def call(self, prompt: str, temperature: float = 0.1, max_tokens: int = 4096) -> str: ...


def _strip_code_fences(text: str) -> str:
    """Strip markdown code fences from LLM response."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


class LLMClient:
    """Unified LLM client with provider chain, JSON retry, and usage tracking.

    Provider chain (tries in order):
    1. Primary provider (subscription or preferred API)
    2. Fallback provider (if primary fails or quota exhausted)

    Usage is tracked per call for cost visibility.
    """

    def __init__(
        self,
        provider: LLMProvider,
        provider_name: str = "unknown",
        fallback: LLMProvider | None = None,
        fallback_name: str = "unknown",
        usage_conn_factory: Any = None,
    ) -> None:
        self.provider = provider
        self.provider_name = provider_name
        self.fallback = fallback
        self.fallback_name = fallback_name
        self._usage_conn_factory = usage_conn_factory  # async callable returning asyncpg.Connection

    async def call(
        self,
        prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        purpose: str = "general",
    ) -> str:
        """Make an LLM call. Tries primary, falls back if it fails."""
        # Try primary
        try:
            result = await self._call_provider(
                self.provider, self.provider_name, prompt, temperature, max_tokens, purpose
            )
            return result
        except Exception as primary_err:
            if not self.fallback:
                raise

            logger.warning(
                "Primary provider %s failed, falling back to %s: %s",
                self.provider_name,
                self.fallback_name,
                primary_err,
            )

        # Try fallback
        return await self._call_provider(self.fallback, self.fallback_name, prompt, temperature, max_tokens, purpose)

    async def _call_provider(
        self,
        provider: LLMProvider,
        name: str,
        prompt: str,
        temperature: float,
        max_tokens: int,
        purpose: str,
    ) -> str:
        """Call a specific provider with logging and usage tracking."""
        start = time.monotonic()
        try:
            result = await provider.call(prompt, temperature=temperature, max_tokens=max_tokens)
            elapsed_ms = round((time.monotonic() - start) * 1000)
            logger.info(
                "LLM call succeeded",
                extra={
                    "provider": name,
                    "purpose": purpose,
                    "latency_ms": elapsed_ms,
                    "prompt_len": len(prompt),
                    "response_len": len(result),
                },
            )

            # Track usage (non-blocking)
            await self._track_usage(name, prompt, result, purpose)

            return result
        except Exception:
            elapsed_ms = round((time.monotonic() - start) * 1000)
            logger.error(
                "LLM call failed",
                extra={"provider": name, "purpose": purpose, "latency_ms": elapsed_ms},
            )
            raise

    async def _track_usage(self, provider: str, prompt: str, result: str, purpose: str) -> None:
        """Track usage in the database (best-effort, never blocks pipeline)."""
        if not self._usage_conn_factory:
            return
        try:
            from growthclaw.llm.usage_tracker import estimate_cost_cents, estimate_tokens, record_usage

            input_tokens = estimate_tokens(prompt)
            output_tokens = estimate_tokens(result)
            cost = estimate_cost_cents(provider, input_tokens, output_tokens)

            conn = await self._usage_conn_factory()
            try:
                await record_usage(
                    conn,
                    provider=provider,
                    model=self._get_model_name(provider),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    purpose=purpose,
                    cost_cents=cost,
                )
            finally:
                await conn.close()
        except Exception as e:
            logger.debug("Usage tracking skipped: %s", e)

    def _get_model_name(self, provider: str) -> str:
        if provider == "nvidia":
            return "nvidia/nemotron-3-super-120b-a12b"
        if provider == "anthropic":
            return "claude-sonnet-4-20250514"
        return provider

    async def call_json(
        self, prompt: str, temperature: float = 0.1, max_tokens: int = 4096, purpose: str = "general"
    ) -> dict[str, Any]:
        """Make an LLM call and parse the response as JSON. Retries once on parse failure."""
        raw = await self.call(prompt, temperature=temperature, max_tokens=max_tokens, purpose=purpose)
        text = _strip_code_fences(raw)

        try:
            return json.loads(text)  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            logger.warning("JSON parse failed, retrying with fix prompt", extra={"raw_length": len(raw)})

        fix_prompt = f"The following JSON is invalid. Fix it and return ONLY valid JSON, no explanation:\n\n{raw}"
        fixed_raw = await self.call(fix_prompt, temperature=0.0, max_tokens=max_tokens, purpose=f"{purpose}_json_fix")
        fixed_text = _strip_code_fences(fixed_raw)
        return json.loads(fixed_text)  # type: ignore[no-any-return]

    async def call_json_list(
        self, prompt: str, temperature: float = 0.1, max_tokens: int = 4096, purpose: str = "general"
    ) -> list[Any]:
        """Make an LLM call and parse the response as a JSON array."""
        raw = await self.call(prompt, temperature=temperature, max_tokens=max_tokens, purpose=purpose)
        text = _strip_code_fences(raw)

        try:
            result = json.loads(text)
            if isinstance(result, list):
                return result
            raise json.JSONDecodeError("Expected array", text, 0)
        except json.JSONDecodeError:
            logger.warning("JSON array parse failed, retrying with fix prompt")

        fix_prompt = (
            f"The following should be a JSON array. Fix it and return ONLY a valid JSON array, no explanation:\n\n{raw}"
        )
        fixed_raw = await self.call(fix_prompt, temperature=0.0, max_tokens=max_tokens, purpose=f"{purpose}_json_fix")
        fixed_text = _strip_code_fences(fixed_raw)
        return json.loads(fixed_text)  # type: ignore[no-any-return]


def create_llm_client(
    nvidia_api_key: str | None = None,
    anthropic_api_key: str | None = None,
    nvidia_nim_url: str | None = None,
    usage_conn_factory: Any = None,
) -> LLMClient:
    """Create an LLM client with provider chain based on available keys.

    Provider priority:
    1. NVIDIA NIM (if nvidia_api_key set) — primary, Anthropic fallback
    2. Anthropic Claude (if anthropic_api_key set) — primary, no fallback
    3. Raises ValueError if neither is set
    """
    primary: LLMProvider | None = None
    primary_name = "unknown"
    fallback: LLMProvider | None = None
    fallback_name = "unknown"

    if nvidia_api_key:
        from growthclaw.llm.nvidia_nim import NvidiaNimProvider

        primary = NvidiaNimProvider(api_key=nvidia_api_key, nim_url=nvidia_nim_url)
        primary_name = "nvidia"

        # If Anthropic is also available, use as fallback
        if anthropic_api_key:
            from growthclaw.llm.anthropic_fallback import AnthropicProvider

            fallback = AnthropicProvider(api_key=anthropic_api_key)
            fallback_name = "anthropic"

    elif anthropic_api_key:
        from growthclaw.llm.anthropic_fallback import AnthropicProvider

        primary = AnthropicProvider(api_key=anthropic_api_key)
        primary_name = "anthropic"

    if primary is None:
        raise ValueError("No LLM API key configured (need NVIDIA_API_KEY or ANTHROPIC_API_KEY)")

    return LLMClient(
        provider=primary,
        provider_name=primary_name,
        fallback=fallback,
        fallback_name=fallback_name,
        usage_conn_factory=usage_conn_factory,
    )
