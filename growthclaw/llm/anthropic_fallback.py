"""Anthropic Claude LLM provider with per-task model routing."""

from __future__ import annotations

import anthropic

# Model routing: creative tasks get Opus, analytical tasks get Sonnet
SONNET_MODEL = "claude-sonnet-4-6"
OPUS_MODEL = "claude-opus-4-6"

# Purposes that benefit from Opus creativity
_OPUS_PURPOSES = frozenset({
    "compose_sms",
    "compose_email",
    "compose_sms_retry",
    "nightly_sweep",
    "hypothesis_generation",
    "variant_creation",
    "prompt_optimization",
    "dag_compact_trigger",
    "dag_condense_patterns",
    "dag_synthesize_strategy",
})


def model_for_purpose(purpose: str) -> str:
    """Select the appropriate model based on task purpose."""
    if purpose in _OPUS_PURPOSES:
        return OPUS_MODEL
    return SONNET_MODEL


class AnthropicProvider:
    """Anthropic Claude provider with per-task model routing.

    Creative tasks (message composition, hypothesis generation) use Opus 4.6.
    Analytical tasks (schema classification, evaluation) use Sonnet 4.6.
    """

    def __init__(self, api_key: str) -> None:
        self.client = anthropic.AsyncAnthropic(api_key=api_key)

    async def call(
        self,
        prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        purpose: str = "general",
    ) -> str:
        model = model_for_purpose(purpose)
        message = await self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
        )
        return message.content[0].text  # type: ignore[union-attr]
