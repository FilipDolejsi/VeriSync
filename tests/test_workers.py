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
    provider="ollama",
    cost_sats=5,
    endpoint_url="http://localhost:8000/worker/llama3-8b",
    capability_tags=["style"],
)

ANTHROPIC_MODEL = ModelEntry(
    id="claude-haiku",
    name="claude-haiku-4-5",
    provider="anthropic",
    cost_sats=40,
    endpoint_url="http://localhost:8000/worker/claude-haiku",
    capability_tags=["security"],
)


# ── handler.dispatch ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dispatch_ollama():
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
    assert "llama3:8b" in str(call_args)


@pytest.mark.asyncio
async def test_dispatch_anthropic():
    mock_content = MagicMock()
    mock_content.text = "security issue found"

    mock_message = MagicMock()
    mock_message.content = [mock_content]

    mock_anthropic_client = AsyncMock()
    mock_anthropic_client.messages.create = AsyncMock(return_value=mock_message)

    with patch("workers.handler.anthropic.AsyncAnthropic") as mock_cls:
        mock_cls.return_value = mock_anthropic_client
        result = await dispatch("review this code", ANTHROPIC_MODEL)

    assert result == "security issue found"
    mock_anthropic_client.messages.create.assert_called_once()


@pytest.mark.asyncio
async def test_dispatch_unknown_provider_raises():
    bad_model = ModelEntry(
        id="unknown",
        name="unknown",
        provider="ollama",  # valid literal
        cost_sats=0,
        endpoint_url="",
        capability_tags=[],
    )
    bad_model.__dict__["provider"] = "unknown_provider"

    with pytest.raises(ValueError, match="Unknown provider"):
        await dispatch("task", bad_model)

