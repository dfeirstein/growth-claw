"""Anthropic Claude fallback LLM provider."""

from __future__ import annotations

import anthropic

ANTHROPIC_MODEL = "claude-sonnet-4-20250514"


class AnthropicProvider:
    """Anthropic Claude provider using the official SDK."""

    def __init__(self, api_key: str) -> None:
        self.client = anthropic.AsyncAnthropic(api_key=api_key)

    async def call(self, prompt: str, temperature: float = 0.1, max_tokens: int = 4096) -> str:
        message = await self.client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
        )
        return message.content[0].text  # type: ignore[union-attr]
