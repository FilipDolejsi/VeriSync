import hashlib
import hmac
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# ── Stubs (before any app imports) ───────────────────────────────────────────

_mock_store = MagicMock()
_mock_store.init_db = AsyncMock()
sys.modules.setdefault("db", MagicMock())
sys.modules["db.store"] = _mock_store

sys.modules.setdefault("payments", MagicMock())
sys.modules["payments.wallet"] = MagicMock()

_mock_registry = MagicMock()
_mock_registry.load_registry = MagicMock(return_value=[])
sys.modules.setdefault("registry", MagicMock())
sys.modules["registry.loader"] = _mock_registry

_mock_factory = MagicMock()
_mock_factory.create_worker_router = MagicMock(return_value=MagicMock(routes=[]))
sys.modules.setdefault("workers", MagicMock())
sys.modules["workers.factory"] = _mock_factory

os.environ.setdefault("SESSION_SECRET_KEY", "test-secret")
os.environ.setdefault("GITHUB_CLIENT_ID", "test-id")
os.environ.setdefault("GITHUB_CLIENT_SECRET", "test-secret")
os.environ.setdefault("GITHUB_REDIRECT_URI", "http://test/auth/callback")

from main import app  # noqa: E402

WEBHOOK_SECRET = "test_webhook_secret_abc123"
WATCHED = {"webhook_secret": WEBHOOK_SECRET, "user_id": "user-123"}


def _sign(payload: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def _pr_payload(action: str, base_ref: str = "main") -> dict:
    return {
        "action": action,
        "repository": {"full_name": "testuser/testrepo"},
        "pull_request": {"number": 42, "base": {"ref": base_ref}, "merged": False},
    }


def _push_payload(ref: str = "refs/heads/main") -> dict:
    return {
        "ref": ref,
        "before": "abc123",
        "after": "def456",
        "repository": {"full_name": "testuser/testrepo"},
    }


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# Patch at the point of use so import-time binding doesn't matter
@pytest_asyncio.fixture(autouse=True)
async def patch_db(request):
    mock_db = AsyncMock()
    mock_get_db = MagicMock()
    mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)

    watched = None if "unregistered" in request.node.name else WATCHED

    with (
        patch("gh.webhook.get_db", mock_get_db),
        patch("gh.webhook.get_watched_repo", new_callable=AsyncMock, return_value=watched),
        patch("gh.webhook.get_github_token", new_callable=AsyncMock, return_value="ghp_fake"),
    ):
        yield


# ── Signature validation ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_missing_signature_returns_403(client):
    payload = json.dumps(_pr_payload("opened")).encode()
    response = await client.post(
        "/webhook/github",
        content=payload,
        headers={"Content-Type": "application/json", "X-GitHub-Event": "pull_request"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_invalid_signature_returns_403(client):
    payload = json.dumps(_pr_payload("opened")).encode()
    response = await client.post(
        "/webhook/github",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": "sha256=wrong",
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_valid_signature_passes(client):
    payload = json.dumps(_pr_payload("labeled")).encode()
    sig = _sign(payload, WEBHOOK_SECRET)
    response = await client.post(
        "/webhook/github",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": sig,
        },
    )
    assert response.status_code == 200


# ── Event routing ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pr_opened_enqueues_review(client):
    payload = json.dumps(_pr_payload("opened")).encode()
    sig = _sign(payload, WEBHOOK_SECRET)
    with patch("gh.webhook.fetch_pr_diff", return_value={"diff": "...", "url": "http://x"}):
        response = await client.post(
            "/webhook/github",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": sig,
            },
        )
    assert response.json()["status"] == "accepted"
    assert "pr_id" in response.json()


@pytest.mark.asyncio
async def test_pr_targeting_non_main_is_ignored(client):
    payload = json.dumps(_pr_payload("opened", base_ref="feature")).encode()
    sig = _sign(payload, WEBHOOK_SECRET)
    response = await client.post(
        "/webhook/github",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": sig,
        },
    )
    assert response.json()["status"] == "ignored"


@pytest.mark.asyncio
async def test_push_to_main_enqueues_review(client):
    payload = json.dumps(_push_payload("refs/heads/main")).encode()
    sig = _sign(payload, WEBHOOK_SECRET)
    with patch("gh.webhook.fetch_push_diff", return_value={"diff": "...", "url": "http://x"}):
        response = await client.post(
            "/webhook/github",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": sig,
            },
        )
    assert response.json()["status"] == "accepted"


@pytest.mark.asyncio
async def test_push_to_non_main_is_ignored(client):
    payload = json.dumps(_push_payload("refs/heads/feature")).encode()
    sig = _sign(payload, WEBHOOK_SECRET)
    response = await client.post(
        "/webhook/github",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": sig,
        },
    )
    assert response.json()["status"] == "ignored"


@pytest.mark.asyncio
async def test_unregistered_repo_is_ignored(client):
    payload = json.dumps(_pr_payload("opened")).encode()
    sig = _sign(payload, WEBHOOK_SECRET)
    response = await client.post(
        "/webhook/github",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": sig,
        },
    )
    assert response.json()["status"] == "ignored"
