import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Stub db.store and payments.wallet before importing the app
_mock_store = MagicMock()
_mock_store.get_db = MagicMock()
_mock_store.upsert_user = AsyncMock()
_mock_store.get_user_by_github_id = AsyncMock(return_value=None)
_mock_store.get_user_by_id = AsyncMock(return_value=None)
_mock_store.init_db = AsyncMock()
sys.modules.setdefault("db", MagicMock())
sys.modules["db.store"] = _mock_store

os.environ.setdefault("SESSION_SECRET_KEY", "test-secret-not-for-prod")
os.environ.setdefault("GITHUB_CLIENT_ID", "test-client-id")
os.environ.setdefault("GITHUB_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("GITHUB_REDIRECT_URI", "http://test/auth/callback")

from main import app  # noqa: E402


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_login_redirects_to_github(client):
    response = await client.get("/auth/login", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert "github.com/login/oauth/authorize" in response.headers["location"]


@pytest.mark.asyncio
async def test_callback_stores_session_and_redirects_to_dashboard(client):
    fake_profile = {
        "id": 123456,
        "login": "filiptest",
        "avatar_url": "https://avatars.githubusercontent.com/u/123456",
    }

    mock_gh_response = MagicMock()
    mock_gh_response.json.return_value = fake_profile
    mock_gh_response.raise_for_status = MagicMock()

    mock_http_client = AsyncMock()
    mock_http_client.get.return_value = mock_gh_response

    mock_db = AsyncMock()

    with (
        patch("auth.github_oauth.oauth.github.authorize_access_token", new_callable=AsyncMock) as mock_token,
        patch("httpx.AsyncClient") as mock_httpx,
        patch("auth.github_oauth.get_db") as mock_get_db,
    ):
        mock_token.return_value = {"access_token": "ghp_fake_token_123"}
        mock_httpx.return_value.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)

        response = await client.get(
            "/auth/callback?code=fake_code&state=fake_state",
            follow_redirects=False,
        )

    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/dashboard"


@pytest.mark.asyncio
async def test_logout_redirects_to_root(client):
    response = await client.get("/auth/logout", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/"


@pytest.mark.asyncio
async def test_get_current_user_returns_none_when_not_logged_in():
    from auth.github_oauth import get_current_user

    mock_request = MagicMock()
    mock_request.session = {}

    result = await get_current_user(mock_request)
    assert result is None
