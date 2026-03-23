"""Embedding generation for memory entries — OpenAI or local sentence-transformers."""

from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger("growthclaw.memory.embedder")

EMBEDDING_DIM = 1536  # OpenAI text-embedding-3-small dimension


async def embed_text(text: str) -> list[float]:
    """Generate an embedding vector for the given text.

    Uses OpenAI text-embedding-3-small if OPENAI_API_KEY is set,
    otherwise falls back to a simple hash-based embedding (for development).
    """
    api_key = os.getenv("OPENAI_API_KEY")

    if api_key:
        return await _embed_openai(text, api_key)
    else:
        logger.warning("No OPENAI_API_KEY set — using hash-based embeddings (not for production)")
        return _embed_hash(text)


async def _embed_openai(text: str, api_key: str) -> list[float]:
    """Generate embedding via OpenAI API."""
    import openai

    client = openai.OpenAI(api_key=api_key)

    def _call() -> list[float]:
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
        )
        return response.data[0].embedding

    return await asyncio.to_thread(_call)


def _embed_hash(text: str) -> list[float]:
    """Simple hash-based pseudo-embedding for development/testing.

    NOT suitable for production — no semantic similarity.
    """
    import hashlib

    h = hashlib.sha512(text.encode()).digest()
    # Expand hash to fill EMBEDDING_DIM
    values = []
    for i in range(EMBEDDING_DIM):
        byte_val = h[i % len(h)]
        values.append((byte_val / 255.0) * 2 - 1)  # Normalize to [-1, 1]
    return values
