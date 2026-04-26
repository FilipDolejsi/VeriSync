import asyncio
import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from db.store import get_db, get_github_token, get_watched_repo
from gh.client import fetch_pr_diff, fetch_push_diff

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory job registry so in-progress reviews can be cancelled on synchronize
_active_jobs: dict[str, asyncio.Task] = {}


# ── Signature validation ──────────────────────────────────────────────────────

def _verify_signature(payload: bytes, secret: str, signature_header: str | None) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


# ── Background review job ─────────────────────────────────────────────────────

async def _run_review(pr_id: str, diff: dict, user_id: str, trigger_type: str):
    """
    Placeholder for the full pipeline call.
    Abdalaziz's pipeline.graph will be wired in here during Phase 3.
    """
    logger.info(
        f"[review:{pr_id}] started — trigger={trigger_type} "
        f"user={user_id} pr={diff.get('url')}"
    )
    # TODO Phase 3: await pipeline.graph.run(pr_id, diff, user_id)
    _active_jobs.pop(pr_id, None)


# ── Webhook endpoint ──────────────────────────────────────────────────────────

@router.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_github_event: str | None = Header(default=None),
    x_hub_signature_256: str | None = Header(default=None),
):
    payload = await request.body()
    body = await request.json()

    repo_full_name = (
        body.get("repository", {}).get("full_name")
        or body.get("pull_request", {}).get("head", {}).get("repo", {}).get("full_name")
    )
    if not repo_full_name:
        raise HTTPException(status_code=400, detail="Cannot determine repository")

    # Look up webhook secret and owner for this repo
    async with get_db() as db:
        watched = await get_watched_repo(db, repo_full_name)
        if not watched:
            # Repo not registered — ignore silently
            return {"status": "ignored", "reason": "repo not watched"}

        if not _verify_signature(payload, watched["webhook_secret"], x_hub_signature_256):
            raise HTTPException(status_code=403, detail="Invalid signature")

        github_token = await get_github_token(db, watched["user_id"])

    if not github_token:
        raise HTTPException(status_code=500, detail="No GitHub token for repo owner")

    user_id = watched["user_id"]

    # ── pull_request event ────────────────────────────────────────────────────
    if x_github_event == "pull_request":
        action = body.get("action")
        pr = body.get("pull_request", {})
        base_ref = pr.get("base", {}).get("ref", "")

        if base_ref != "main":
            return {"status": "ignored", "reason": "not targeting main"}

        if action in ("opened", "synchronize"):
            pr_number = pr["number"]
            pr_id = str(uuid.uuid4())

            # Cancel any in-progress review for this PR on synchronize
            job_key = f"{repo_full_name}#{pr_number}"
            if job_key in _active_jobs:
                _active_jobs[job_key].cancel()
                logger.info(f"Cancelled stale review for {job_key}")

            diff = fetch_pr_diff(repo_full_name, pr_number, github_token)
            trigger = "pr_opened" if action == "opened" else "pr_updated"

            task = asyncio.create_task(
                _run_review(pr_id, diff, user_id, trigger)
            )
            _active_jobs[job_key] = task
            logger.info(f"Enqueued review {pr_id} for {job_key}")
            return {"status": "accepted", "pr_id": pr_id}

        if action == "closed" and pr.get("merged"):
            logger.info(f"PR merged: {repo_full_name}#{pr.get('number')}")
            # TODO: mark PR as merged in DB, trigger router retrain check
            return {"status": "merged"}

        return {"status": "ignored", "reason": f"action={action} not handled"}

    # ── push event ────────────────────────────────────────────────────────────
    if x_github_event == "push":
        if body.get("ref") != "refs/heads/main":
            return {"status": "ignored", "reason": "not main branch"}

        before = body.get("before")
        after = body.get("after")

        if not before or not after:
            return {"status": "ignored", "reason": "missing SHAs"}

        pr_id = str(uuid.uuid4())
        diff = fetch_push_diff(repo_full_name, before, after, github_token)

        task = asyncio.create_task(
            _run_review(pr_id, diff, user_id, "direct_push")
        )
        _active_jobs[f"{repo_full_name}@{after[:7]}"] = task
        logger.info(f"Enqueued push review {pr_id} for {repo_full_name}")
        return {"status": "accepted", "pr_id": pr_id}

    return {"status": "ignored", "reason": f"event={x_github_event} not handled"}
