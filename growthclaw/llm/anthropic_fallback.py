"""Anthropic Claude LLM provider with per-task model routing and streaming."""

from __future__ import annotations

import anthropic

# Model routing: creative tasks get Opus, analytical tasks get Sonnet
SONNET_MODEL = "claude-sonnet-4-6"
OPUS_MODEL = "claude-opus-4-6"

# Max output tokens per model (API requires this parameter)
_MAX_TOKENS = {
    SONNET_MODEL: 64000,
    OPUS_MODEL: 128000,
}

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

    Uses streaming to avoid the SDK's 10-minute timeout on large max_tokens.
    Creative tasks (message composition, hypothesis generation) use Opus 4.6.
    Analytical tasks (schema classification, evaluation) use Sonnet 4.6.
    """

    def __init__(self, api_key: str) -> None:
        self.client = anthropic.AsyncAnthropic(api_key=api_key)

    async def call(
        self,
        prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 0,
        purpose: str = "general",
    ) -> str:
        model = model_for_purpose(purpose)
        actual_max = _MAX_TOKENS.get(model, 64000)

        # Use streaming to avoid SDK timeout error on large max_tokens.
        # The model generates as many tokens as it needs and stops naturally.
        async with self.client.messages.stream(
            model=model,
            max_tokens=actual_max,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
        ) as stream:
            message = await stream.get_final_message()

        return message.content[0].text  # type: ignore[union-attr]
