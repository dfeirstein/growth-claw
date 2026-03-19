"""Unified LLM client with provider selection, JSON parsing, and call logging."""

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
        # Remove opening fence (with optional language tag)
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        # Remove closing fence
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


class LLMClient:
    """Unified LLM client with JSON retry and logging."""

    def __init__(self, provider: LLMProvider, provider_name: str = "unknown") -> None:
        self.provider = provider
        self.provider_name = provider_name

    async def call(self, prompt: str, temperature: float = 0.1, max_tokens: int = 4096) -> str:
        """Make an LLM call with logging."""
        start = time.monotonic()
        try:
            result = await self.provider.call(prompt, temperature=temperature, max_tokens=max_tokens)
            elapsed_ms = round((time.monotonic() - start) * 1000)
            logger.info(
                "LLM call succeeded",
                extra={
                    "provider": self.provider_name,
                    "latency_ms": elapsed_ms,
                    "prompt_len": len(prompt),
                    "response_len": len(result),
                },
            )
            return result
        except Exception:
            elapsed_ms = round((time.monotonic() - start) * 1000)
            logger.error(
                "LLM call failed",
                extra={"provider": self.provider_name, "latency_ms": elapsed_ms, "prompt_len": len(prompt)},
            )
            raise

    async def call_json(self, prompt: str, temperature: float = 0.1, max_tokens: int = 4096) -> dict[str, Any]:
        """Make an LLM call and parse the response as JSON. Retries once on parse failure."""
        raw = await self.call(prompt, temperature=temperature, max_tokens=max_tokens)
        text = _strip_code_fences(raw)

        try:
            return json.loads(text)  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            logger.warning("JSON parse failed, retrying with fix prompt", extra={"raw_length": len(raw)})

        # Retry with fix prompt
        fix_prompt = f"The following JSON is invalid. Fix it and return ONLY valid JSON, no explanation:\n\n{raw}"
        fixed_raw = await self.call(fix_prompt, temperature=0.0, max_tokens=max_tokens)
        fixed_text = _strip_code_fences(fixed_raw)
        return json.loads(fixed_text)  # type: ignore[no-any-return]

    async def call_json_list(self, prompt: str, temperature: float = 0.1, max_tokens: int = 4096) -> list[Any]:
        """Make an LLM call and parse the response as a JSON array."""
        raw = await self.call(prompt, temperature=temperature, max_tokens=max_tokens)
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
        fixed_raw = await self.call(fix_prompt, temperature=0.0, max_tokens=max_tokens)
        fixed_text = _strip_code_fences(fixed_raw)
        return json.loads(fixed_text)  # type: ignore[no-any-return]


def create_llm_client(nvidia_api_key: str | None, anthropic_api_key: str | None) -> LLMClient:
    """Create an LLM client based on available API keys."""
    if nvidia_api_key:
        from growthclaw.llm.nvidia_nim import NvidiaNimProvider

        provider = NvidiaNimProvider(api_key=nvidia_api_key)
        return LLMClient(provider=provider, provider_name="nvidia")
    elif anthropic_api_key:
        from growthclaw.llm.anthropic_fallback import AnthropicProvider

        provider = AnthropicProvider(api_key=anthropic_api_key)
        return LLMClient(provider=provider, provider_name="anthropic")
    else:
        raise ValueError("No LLM API key configured")
