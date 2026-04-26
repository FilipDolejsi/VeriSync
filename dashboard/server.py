import os
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

from auth.github_oauth import get_current_user
from db.store import (
    get_db,
    get_pr_history,
    get_spend_analytics,
    get_finding_analytics,
    list_watched_repos,
    get_watched_repo,
    store_watched_repo,
    deactivate_watched_repo,
)
from gh.client import get_user_repos, register_webhook, delete_webhook

router = APIRouter()
STATIC = Path(__file__).parent / "static"


# ── Pages ─────────────────────────────────────────────────────────────────────

@router.get("/")
async def index(request: Request):
    user = await get_current_user(request)
    if user:
        return RedirectResponse(url="/dashboard")
    return FileResponse(STATIC / "index.html")


@router.get("/dashboard")
async def dashboard(request: Request):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login")
    return FileResponse(STATIC / "dashboard.html")


@router.get("/graph")
async def graph(request: Request):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login")
    return FileResponse(STATIC / "graph.html")


@router.get("/docs")
async def docs(request: Request):
    return FileResponse(STATIC / "docs.html")


# ── Auth state ────────────────────────────────────────────────────────────────

@router.get("/api/me")
async def me(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)
    return user


# ── Data API ──────────────────────────────────────────────────────────────────

@router.get("/api/history")
async def history(request: Request, limit: int = 20, offset: int = 0):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)
    async with get_db() as db:
        return await get_pr_history(db, user["id"], limit, offset)


@router.get("/api/analytics")
async def analytics(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)
    async with get_db() as db:
        spend = await get_spend_analytics(db, user["id"])
        findings = await get_finding_analytics(db, user["id"])
    return {"spend": spend, "findings": findings}


@router.get("/api/repos")
async def list_repos(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)
    token = request.session.get("github_token")
    return get_user_repos(token)


@router.get("/api/watched")
async def list_watched(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)
    async with get_db() as db:
        return await list_watched_repos(db, user["id"])


class WatchRequest(BaseModel):
    repos: list[str]


@router.post("/repos/watch")
async def watch_repos(body: WatchRequest, request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)
    token = request.session.get("github_token")

    registered, failed = [], []
    async with get_db() as db:
        for repo in body.repos:
            try:
                hook_id, secret = register_webhook(repo, token)
                await store_watched_repo(db, {
                    "id": str(uuid.uuid4()),
                    "user_id": user["id"],
                    "repo_full_name": repo,
                    "webhook_id": hook_id,
                    "webhook_secret": secret,
                    "active": 1,
                })
                registered.append(repo)
            except Exception as e:
                failed.append({"repo": repo, "error": str(e)})

    return {"registered": registered, "failed": failed}


@router.post("/repos/unwatch")
async def unwatch_repo(request: Request, repo_full_name: str):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)
    token = request.session.get("github_token")

    async with get_db() as db:
        watched = await get_watched_repo(db, repo_full_name)
        if watched and watched["user_id"] == user["id"]:
            delete_webhook(repo_full_name, token, watched["webhook_id"])
            await deactivate_watched_repo(db, user["id"], repo_full_name)

    return {"status": "unwatched"}
