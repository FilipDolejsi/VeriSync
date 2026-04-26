import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ.setdefault("USE_MOCK_WALLET", "true")

sys.modules.setdefault("payments", MagicMock())
_mock_wallet_mod = MagicMock()
_mock_wallet_instance = MagicMock()
_mock_wallet_instance.pay = MagicMock()
_mock_wallet_mod.get_wallet = MagicMock(return_value=_mock_wallet_instance)
sys.modules["payments.wallet"] = _mock_wallet_mod

from models import ModelEntry  # noqa: E402
from workers.handler import dispatch  # noqa: E402


OLLAMA_MODEL = ModelEntry(
    id="llama3-8b",
    name="llama3:8b",
    provider="qrok-api",
    cost_sats=5,
    endpoint_url="http://localhost:8000/worker/llama3-8b",
    capability_tags=["style"],
)

ANTHROPIC_MODEL = ModelEntry(
    id="claude-haiku",
    name="claude-haiku-4-5",
    provider="gemini",
    cost_sats=40,
    endpoint_url="http://localhost:8000/worker/gemini-pro",
    capability_tags=["security"],
)


# ── handler.dispatch ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dispatch_qrok_api():
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": "looks good"}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response

    with patch("workers.handler.httpx.AsyncClient") as mock_httpx:
        mock_httpx.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await dispatch("review this code", OLLAMA_MODEL)

    assert result == "looks good"
    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    assert "8000" in str(call_args)  # Check endpoint_url is in the call


@pytest.mark.asyncio
async def test_dispatch_gemini():
    mock_response = MagicMock()
    mock_response.text = "security issue found"

    mock_genai_client = AsyncMock()
    mock_genai_client.models.generate_content = MagicMock(return_value=mock_response)

    with patch("workers.handler.genai.Client") as mock_cls:
        with patch("workers.handler.GEMINI_API_KEY", "test-gemini-key"):
            mock_cls.return_value = mock_genai_client
            result = await dispatch("review this code", ANTHROPIC_MODEL)

    assert result == "security issue found"


@pytest.mark.asyncio
async def test_dispatch_unknown_provider_raises():
    # Create a model with a valid provider first, then modify it
    bad_model = ModelEntry(
        id="unknown",
        name="unknown",
        provider="qrok-api",
        cost_sats=0,
        endpoint_url="",
        capability_tags=[],
    )
    # Patch the provider attribute directly
    bad_model.provider = "unknown_provider"  # type: ignore

    with pytest.raises(ValueError, match="Unknown provider"):
        await dispatch("task", bad_model)

