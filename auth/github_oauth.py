import os
import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode, urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, RedirectResponse

from db.store import get_db, upsert_user, get_user_by_github_id, get_user_by_id
from payments.wallet import get_wallet

router = APIRouter(prefix="/auth")

CLIENT_ID     = os.environ["GITHUB_CLIENT_ID"]
CLIENT_SECRET = os.environ["GITHUB_CLIENT_SECRET"]
SCOPE         = "repo,read:user,admin:repo_hook"

def _callback_uri() -> str:
    configured = os.environ.get("GITHUB_REDIRECT_URI")
    if configured:
        return configured.rstrip("/")
    backend = os.environ.get("BACKEND_URL") or os.environ.get("RENDER_EXTERNAL_URL", "")
    return backend.rstrip("/") + "/auth/callback"


def _is_safe_redirect(url: str) -> bool:
    if url.startswith("/"):
        return True
    p = urlparse(url)
    return p.scheme in {"http", "https"} and bool(p.netloc)


@router.get("/login")
async def login(request: Request, redirect: str = Query(default="")):
    target = redirect if (redirect and _is_safe_redirect(redirect)) else "/dashboard"
    request.session["post_auth_redirect"] = target

    params = urlencode({
        "client_id":    CLIENT_ID,
        "redirect_uri": _callback_uri(),
        "scope":        SCOPE,
    })
    return RedirectResponse(f"https://github.com/login/oauth/authorize?{params}")


@router.get("/callback")
async def callback(request: Request):
    code = request.query_params.get("code")
    if not code:
        return RedirectResponse(url=f"{FRONTEND_URL}?error=missing_code")

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id":     CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "code":          code,
                "redirect_uri":  _callback_uri(),
            },
            headers={"Accept": "application/json"},
            timeout=15.0,
        )
        token_resp.raise_for_status()
        access_token = token_resp.json().get("access_token")

        if not access_token:
            return RedirectResponse(url="/?error=no_token")

        profile_resp = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15.0,
        )
        profile_resp.raise_for_status()
        profile = profile_resp.json()

    github_id = str(profile["id"])
    now = datetime.now(timezone.utc).isoformat()

    async with get_db() as db:
        existing = await get_user_by_github_id(db, github_id)

        if existing:
            user_id   = existing["id"]
            wallet_id = existing["wallet_id"]
        else:
            user_id   = str(uuid.uuid4())
            wallet_id = get_wallet().create_wallet(user_id)

        await upsert_user(db, {
            "id":          user_id,
            "github_id":   github_id,
            "username":    profile["login"],
            "avatar_url":  profile.get("avatar_url", ""),
            "wallet_id":   wallet_id,
            "sat_balance": existing["sat_balance"] if existing else 0,
            "github_token": access_token,
            "created_at":  existing["created_at"] if existing else now,
            "last_login":  now,
        })

    request.session["user_id"]      = user_id
    request.session["github_token"] = access_token

    redirect_url = request.session.pop("post_auth_redirect", "/dashboard")
    if not _is_safe_redirect(redirect_url):
        redirect_url = "/dashboard"

    return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)


@router.get("/me")
async def me(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {
        "id":         user["id"],
        "login":      user.get("username"),
        "name":       user.get("username"),
        "avatar_url": user.get("avatar_url"),
        "sat_balance": user.get("sat_balance", 0),
    }


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return JSONResponse({"status": "logged out"})


@router.get("/logout")
async def logout_get(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=302)


async def get_current_user(request: Request) -> dict | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    async with get_db() as db:
        return await get_user_by_id(db, user_id)
