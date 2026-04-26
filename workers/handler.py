import os
import httpx
from groq import Groq
from google import genai
from models import ModelEntry

QROK_API_BASE_URL = os.environ.get("QROK_API_BASE_URL", "http://localhost:8000")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")


async def dispatch(task: str, model_entry: ModelEntry) -> str:
    if model_entry.provider == "qrok-api":
        return await _call_qrok_api(task, model_entry.endpoint_url)
    elif model_entry.provider == "gemini":
        return await _call_gemini(task, model_entry.name)
    else:
        raise ValueError(f"Unknown provider: {model_entry.provider}")


async def _call_qrok_api(task: str, endpoint_url: str) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            endpoint_url,
            json={"task": task, "stream": False},
            timeout=45.0,
        )
        resp.raise_for_status()
        return resp.json().get("response", resp.json().get("result", ""))


async def _call_gemini(task: str, model_name: str) -> str:
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not configured")
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model=model_name,
        contents=task,
    )
    return response.text
