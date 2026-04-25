import os
import httpx
import anthropic
from models import ModelEntry

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")


async def dispatch(task: str, model_entry: ModelEntry) -> str:
    if model_entry.provider == "ollama":
        return await _call_ollama(task, model_entry.name)
    elif model_entry.provider == "anthropic":
        return await _call_anthropic(task, model_entry.name)
    else:
        raise ValueError(f"Unknown provider: {model_entry.provider}")


async def _call_ollama(task: str, model_name: str) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={"model": model_name, "prompt": task, "stream": False},
            timeout=45.0,
        )
        resp.raise_for_status()
        return resp.json()["response"]


async def _call_anthropic(task: str, model_name: str) -> str:
    client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = await client.messages.create(
        model=model_name,
        max_tokens=1000,
        messages=[{"role": "user", "content": task}],
    )
    return message.content[0].text
