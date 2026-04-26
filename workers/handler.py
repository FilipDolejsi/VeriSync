import os
from groq import Groq
from google import genai
from models import ModelEntry

GROQ_API_KEY   = os.environ.get("GROQ_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


async def dispatch(task: str, model_entry: ModelEntry) -> str:
    if model_entry.provider == "groq-api":
        return _call_groq(task, model_entry.name)
    elif model_entry.provider == "gemini":
        return _call_gemini(task, model_entry.name)
    else:
        raise ValueError(f"Unknown provider: {model_entry.provider}")


def _call_groq(task: str, model_name: str) -> str:
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not set")
    client = Groq(api_key=GROQ_API_KEY)
    resp = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": task}],
        max_tokens=1500,
        temperature=0.3,
        timeout=45,
    )
    return resp.choices[0].message.content


def _call_gemini(task: str, model_name: str) -> str:
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not set")
    client = genai.Client(api_key=GEMINI_API_KEY)
    resp = client.models.generate_content(model=model_name, contents=task)
    return resp.text
