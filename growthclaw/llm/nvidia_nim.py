"""NVIDIA NIM (Nemotron) LLM provider via OpenAI-compatible API."""

from __future__ import annotations

import os

import httpx

DEFAULT_NIM_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_MODEL = "nvidia/nemotron-3-super-120b-a12b"


class NvidiaNimProvider:
    """NVIDIA NIM provider using the OpenAI-compatible chat completions endpoint.

    Supports both cloud-hosted NIM and self-hosted (local GPU) NIM.
    Set nim_url to point to a local instance: http://localhost:8000/v1
    """

    def __init__(self, api_key: str, nim_url: str | None = None) -> None:
        self.api_key = api_key
        base_url = nim_url or os.getenv("NVIDIA_NIM_URL", DEFAULT_NIM_URL)
        self.url = f"{base_url.rstrip('/')}/chat/completions"

    async def call(
        self, prompt: str, temperature: float = 0.1, max_tokens: int = 16384, purpose: str = "general"
    ) -> str:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                self.url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": NVIDIA_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]  # type: ignore[no-any-return]
