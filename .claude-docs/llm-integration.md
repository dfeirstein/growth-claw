# LLM Integration Patterns for GrowthClaw

## Provider Architecture

GrowthClaw uses a unified LLM client with two providers:
1. **Primary**: NVIDIA NIM (Nemotron 3 Super 120B) — OpenAI-compatible API
2. **Fallback**: Anthropic Claude (claude-sonnet-4-20250514) — native SDK

Selection: use NVIDIA if `NVIDIA_API_KEY` is set, otherwise Anthropic.

## NVIDIA NIM API

OpenAI-compatible endpoint at `https://integrate.api.nvidia.com/v1`:

```python
import httpx

async def call_nvidia(prompt: str) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "nvidia/nemotron-3-super-120b-a12b",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 4096,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
```

## Anthropic Claude Fallback

Using the official anthropic SDK:

```python
import anthropic

client = anthropic.AsyncAnthropic(api_key=api_key)

async def call_anthropic(prompt: str) -> str:
    message = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    return message.content[0].text
```

## JSON Response Parsing

Every LLM call that expects structured data must:

1. Request JSON in the prompt
2. Attempt to parse the response
3. On parse failure, send a "fix this JSON" retry prompt
4. On second failure, log and raise

```python
import json

async def call_json(prompt: str) -> dict:
    raw = await call(prompt)

    # Strip markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Retry with fix prompt
        fix_prompt = f"The following JSON is invalid. Fix it and return ONLY valid JSON:\n\n{raw}"
        fixed = await call(fix_prompt)
        fixed_text = fixed.strip()
        if fixed_text.startswith("```"):
            fixed_text = fixed_text.split("\n", 1)[1]
            fixed_text = fixed_text.rsplit("```", 1)[0]
        return json.loads(fixed_text)  # Let this raise if still invalid
```

## Call Logging

Every LLM call must be logged with:
- Prompt (or prompt hash for long prompts)
- Provider used (nvidia/anthropic)
- Response text
- Latency (ms)
- Token usage if available
- Success/failure

Use structlog for structured logging:

```python
import structlog
import time

logger = structlog.get_logger()

async def call_with_logging(prompt: str, purpose: str) -> str:
    start = time.monotonic()
    try:
        result = await provider.call(prompt)
        elapsed = (time.monotonic() - start) * 1000
        logger.info("llm_call", purpose=purpose, provider=provider_name,
                     latency_ms=round(elapsed), response_len=len(result))
        return result
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        logger.error("llm_call_failed", purpose=purpose, provider=provider_name,
                      latency_ms=round(elapsed), error=str(e))
        raise
```

## Prompt Template Rendering

All prompts are Jinja2 templates in `growthclaw/prompts/`:

```python
from jinja2 import Environment, PackageLoader

env = Environment(loader=PackageLoader("growthclaw", "prompts"))

def render(template_name: str, **kwargs) -> str:
    template = env.get_template(template_name)
    return template.render(**kwargs)
```

## Temperature Guidelines

- Schema classification: 0.1 (deterministic)
- Funnel analysis: 0.1 (deterministic)
- Trigger proposal: 0.3 (some creativity)
- Message composition: 0.7 (creative, personalized)
- Experiment analysis: 0.1 (analytical)
