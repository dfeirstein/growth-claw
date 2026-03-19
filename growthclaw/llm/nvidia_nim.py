"""NVIDIA NIM (Nemotron) LLM provider via OpenAI-compatible API."""

from __future__ import annotations

import httpx

NVIDIA_NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
NVIDIA_MODEL = "nvidia/nemotron-3-super-120b-a12b"


class NvidiaNimProvider:
    """NVIDIA NIM provider using the OpenAI-compatible chat completions endpoint."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def call(self, prompt: str, temperature: float = 0.1, max_tokens: int = 4096) -> str:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                NVIDIA_NIM_URL,
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
