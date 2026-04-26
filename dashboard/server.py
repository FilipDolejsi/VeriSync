import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

from auth.github_oauth import get_current_user
from db.store import (
    get_db,
    get_user_history,
    get_analytics,
    get_watched_repo,
    store_watched_repo,
    deactivate_watched_repo,
)
from gh.client import get_user_repos, register_webhook, delete_webhook

router = APIRouter()
STATIC = Path(__file__).parent / "static"


# ── Pages (served from dashboard/static/) ─────────────────────────────────────

@router.get("/")
async def index(request: Request):
    user = await get_current_user(request)
    if user:
        return RedirectResponse(url="/dashboard")
    return FileResponse(STATIC / "index.html")


@router.get("/dashboard")
async def dashboard_page(request: Request):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login")
    return FileResponse(STATIC / "dashboard.html")


@router.get("/graph")
async def graph_page(request: Request):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login")
    return FileResponse(STATIC / "graph.html")


@router.get("/docs")
async def docs_page(request: Request):
    return FileResponse(STATIC / "docs.html")


# ── Auth ──────────────────────────────────────────────────────────────────────

@router.get("/api/me")
async def api_me(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)
    return {
        "id":          user["id"],
        "login":       user.get("username"),
        "name":        user.get("username"),
        "avatar_url":  user.get("avatar_url"),
        "sat_balance": user.get("sat_balance", 0),
    }


# ── Data API ──────────────────────────────────────────────────────────────────

@router.get("/api/history")
async def history(request: Request, limit: int = 20, offset: int = 0):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)
    rows = await get_user_history(user["id"])
    return rows[offset: offset + limit]


@router.get("/api/analytics")
async def analytics(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)
    return await get_analytics(user["id"])


@router.get("/api/repos")
async def list_repos(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)
    token = request.session.get("github_token")
    try:
        return get_user_repos(token)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
                    "id":             str(uuid.uuid4()),
                    "user_id":        user["id"],
                    "repo_full_name": repo,
                    "webhook_id":     hook_id,
                    "webhook_secret": secret,
                    "active":         1,
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
            try:
                delete_webhook(repo_full_name, token, watched["webhook_id"])
            except Exception:
                pass
            await deactivate_watched_repo(db, user["id"], repo_full_name)

    return {"status": "unwatched"}
