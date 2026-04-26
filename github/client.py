import os
import secrets
import ipaddress
from urllib.parse import urlparse

from github import Github, GithubException


def _gh(token: str) -> Github:
    return Github(token)


def get_user_repos(token: str) -> list[dict]:
    return [
        {"full_name": r.full_name, "private": r.private}
        for r in _gh(token).get_user().get_repos(sort="updated")
    ]


def _is_public_webhook_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme not in {"http", "https"}:
        return False

    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        return False

    if hostname in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return False

    if hostname.endswith(".local"):
        return False

    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified:
            return False
    except ValueError:
        pass

    return True


def _resolve_webhook_url() -> str:
    webhook_url = os.environ.get("WEBHOOK_URL", "").strip()
    if not webhook_url:
        base = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
        if base:
            webhook_url = f"{base}/webhook/github"

    if not webhook_url:
        raise ValueError(
            "Missing WEBHOOK_URL. Set WEBHOOK_URL to a public URL, e.g. "
            "https://<your-domain>/webhook/github or https://<ngrok-id>.ngrok-free.app/webhook/github"
        )

    if not _is_public_webhook_url(webhook_url):
        raise ValueError(
            f"Invalid WEBHOOK_URL '{webhook_url}'. GitHub requires a publicly reachable URL (not localhost/private IP)."
        )

    return webhook_url


def register_webhook(repo_full_name: str, github_token: str) -> tuple[int, str]:
    """Register push+pull_request webhook. Returns (hook_id, secret)."""
    webhook_url = _resolve_webhook_url()
    webhook_secret = secrets.token_hex(32)

    repo = _gh(github_token).get_repo(repo_full_name)
    hook = repo.create_hook(
        name="web",
        config={
            "url": webhook_url,
            "content_type": "json",
            "secret": webhook_secret,
        },
        events=["push", "pull_request"],
        active=True,
    )
    return hook.id, webhook_secret


def delete_webhook(repo_full_name: str, github_token: str, hook_id: int):
    try:
        repo = _gh(github_token).get_repo(repo_full_name)
        repo.get_hook(hook_id).delete()
    except GithubException:
        pass


def fetch_pr_diff(repo_full_name: str, pr_number: int, github_token: str) -> dict:
    repo = _gh(github_token).get_repo(repo_full_name)
    pr = repo.get_pull(pr_number)
    files = pr.get_files()
    diff_text = "\n".join(
        f.patch for f in files if f.patch
    )
    return {
        "number": pr.number,
        "title": pr.title,
        "url": pr.html_url,
        "diff": diff_text,
    }


def fetch_push_diff(repo_full_name: str, before_sha: str, after_sha: str, github_token: str) -> dict:
    repo = _gh(github_token).get_repo(repo_full_name)
    comparison = repo.compare(before_sha, after_sha)
    diff_text = "\n".join(
        f.patch for f in comparison.files if f.patch
    )
    return {
        "number": None,
        "title": f"Direct push {after_sha[:7]}",
        "url": comparison.html_url,
        "diff": diff_text,
    }


def post_review_comment(repo_full_name: str, pr_number: int, findings: list, github_token: str):
    repo = _gh(github_token).get_repo(repo_full_name)
    pr = repo.get_pull(pr_number)

    if not findings:
        pr.create_issue_comment("**VeriSync:** No issues found.")
        return

    lines = ["**VeriSync Review**\n"]
    for f in findings:
        emoji = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(f.get("severity", ""), "⚪")
        lines.append(
            f"{emoji} **{f.get('severity','?').upper()}** — `{f.get('category','')}` "
            f"(line {f.get('line_number', '?')})\n"
            f"{f.get('description','')}\n"
            f"> {f.get('suggestion','')}\n"
        )
    pr.create_issue_comment("\n".join(lines))
