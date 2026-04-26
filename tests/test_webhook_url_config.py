import pytest

from gh.client import _resolve_webhook_url


def test_resolve_webhook_url_rejects_missing_env(monkeypatch):
    monkeypatch.delenv("WEBHOOK_URL", raising=False)
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)

    with pytest.raises(ValueError, match="Missing WEBHOOK_URL"):
        _resolve_webhook_url()


def test_resolve_webhook_url_rejects_localhost(monkeypatch):
    monkeypatch.setenv("WEBHOOK_URL", "http://localhost:8000/webhook/github")
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)

    with pytest.raises(ValueError, match="publicly reachable"):
        _resolve_webhook_url()


def test_resolve_webhook_url_accepts_public_url(monkeypatch):
    monkeypatch.setenv("WEBHOOK_URL", "https://example.com/webhook/github")

    assert _resolve_webhook_url() == "https://example.com/webhook/github"


def test_resolve_webhook_url_uses_public_base_url(monkeypatch):
    monkeypatch.delenv("WEBHOOK_URL", raising=False)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://public.example.com/")

    assert _resolve_webhook_url() == "https://public.example.com/webhook/github"
