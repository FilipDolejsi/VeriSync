import asyncio
import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Request

from db.store import get_db, get_github_token, get_user_by_id, get_watched_repo
from gh.client import fetch_pr_diff, fetch_push_diff
from registry.loader import load_registry

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

async def _run_review(
    pr_id: str,
    diff: dict,
    user_id: str,
    trigger_type: str,
    repo_full_name: str,
    pr_number: int | None,
):
    """
    Full pipeline: chunk diff → run reviews → post GitHub comment → update DB → SSE.
    """
    # Late imports keep module-load fast and avoid circular-import issues.
    # db.store imports are re-resolved here so tests that reload db.store with a
    # test DB_PATH don't end up hitting the module-level MagicMock bindings.
    from db.store import get_db, get_github_token, get_user_by_id  # noqa: F811
    from pipeline.graph import run_pr_review
    from pipeline.chunker import parse_unified_diff
    import models as _models
    from dashboard.events import publish
    from gh.client import post_review_comment

    pr_url = diff.get("url", "")
    now = datetime.now(timezone.utc).isoformat()

    # 1. Fetch user wallet_id and github token from DB
    wallet_id = ""
    github_token = None
    async with get_db() as db:
        user = await get_user_by_id(db, user_id)
        if user:
            wallet_id = user.get("wallet_id", "")
        github_token = await get_github_token(db, user_id)

        # 2. Persist PR record so chunk FK references resolve
        await db.execute(
            """
            INSERT OR IGNORE INTO pull_requests
                (id, user_id, repo_full_name, pr_number, pr_title, pr_url,
                 trigger_type, status, started_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'running', ?)
            """,
            (
                pr_id, user_id, repo_full_name, pr_number,
                diff.get("title", ""), pr_url, trigger_type, now,
            ),
        )
        await db.commit()

    # 3. Parse diff into chunks
    raw_diff = diff.get("diff", "")
    raw_chunks = parse_unified_diff(raw_diff)

    # Convert chunker.PRChunk (dataclass) → models.PRChunk (Pydantic)
    model_chunks: list[_models.PRChunk] = []
    for i, rc in enumerate(raw_chunks):
        lines_changed = sum(1 for ln in rc.lines if ln.startswith(("+", "-")))
        model_chunks.append(
            _models.PRChunk(
                id=str(uuid.uuid4()),
                pr_id=pr_id,
                file_path=rc.file,
                hunk_index=i,
                language=rc.detected_language or "unknown",
                diff_text="\n".join(rc.lines),
                lines_changed=lines_changed,
            )
        )

    # 4. Persist chunk records
    if model_chunks:
        async with get_db() as db:
            for mc in model_chunks:
                await db.execute(
                    """
                    INSERT OR IGNORE INTO chunks
                        (id, pr_id, file_path, hunk_index, language, lines_changed)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (mc.id, mc.pr_id, mc.file_path, mc.hunk_index, mc.language, mc.lines_changed),
                )
            await db.commit()

    # 5. SSE: review started
    await publish(user_id, {
        "type": "review_started",
        "pr_id": pr_id,
        "pr_url": pr_url,
        "chunk_count": len(model_chunks),
    })

    # 6. Run pipeline
    registry = load_registry()
    budget = 1000  # sats

    try:
        if model_chunks:
            report = await run_pr_review(
                pr_id=pr_id,
                chunks=model_chunks,
                user_id=user_id,
                registry=registry,
                budget=budget,
                wallet_id=wallet_id,
                pr_url=pr_url,
            )
        else:
            from pipeline.nodes import ReviewReport
            report = ReviewReport(
                pr_id=pr_id,
                pr_url=pr_url,
                total_cost_sats=0,
                total_chunks=0,
                chunks_reviewed=0,
                summary="No diff content to review.",
                priority_actions=[],
                all_findings=[],
            )

        # 7. Post GitHub comment with findings
        if pr_number and github_token:
            findings_dicts = [f.model_dump() for f in report.all_findings]
            post_review_comment(repo_full_name, pr_number, findings_dicts, github_token)

        # 8. Update PR status in DB
        async with get_db() as db:
            await db.execute(
                """
                UPDATE pull_requests
                SET status = 'done', total_cost_sats = ?, completed_at = ?
                WHERE id = ?
                """,
                (report.total_cost_sats, datetime.now(timezone.utc).isoformat(), pr_id),
            )
            await db.commit()

        # 9. SSE: review done
        await publish(user_id, {
            "type": "review_done",
            "pr_id": pr_id,
            "pr_url": pr_url,
            "total_cost_sats": report.total_cost_sats,
            "findings_count": len(report.all_findings),
        })

        logger.info(
            f"[review:{pr_id}] complete — cost={report.total_cost_sats} sats, "
            f"findings={len(report.all_findings)}"
        )

    except Exception as e:
        logger.error(f"[review:{pr_id}] failed: {e}")
        async with get_db() as db:
            await db.execute(
                "UPDATE pull_requests SET status = 'failed' WHERE id = ?", (pr_id,)
            )
            await db.commit()
        await publish(user_id, {"type": "review_failed", "pr_id": pr_id, "error": str(e)})

    finally:
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
                _run_review(pr_id, diff, user_id, trigger, repo_full_name, pr_number)
            )
            _active_jobs[job_key] = task
            logger.info(f"Enqueued review {pr_id} for {job_key}")
            return {"status": "accepted", "pr_id": pr_id}

        if action == "closed" and pr.get("merged"):
            logger.info(f"PR merged: {repo_full_name}#{pr.get('number')}")
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
            _run_review(pr_id, diff, user_id, "direct_push", repo_full_name, None)
        )
        _active_jobs[f"{repo_full_name}@{after[:7]}"] = task
        logger.info(f"Enqueued push review {pr_id} for {repo_full_name}")
        return {"status": "accepted", "pr_id": pr_id}

    return {"status": "ignored", "reason": f"event={x_github_event} not handled"}
