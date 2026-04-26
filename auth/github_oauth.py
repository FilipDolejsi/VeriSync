import os
import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from db.store import get_db, upsert_user, get_user_by_github_id, get_user_by_id
from payments.wallet import get_wallet

router = APIRouter(prefix="/auth")

CLIENT_ID     = os.environ["GITHUB_CLIENT_ID"]
CLIENT_SECRET = os.environ["GITHUB_CLIENT_SECRET"]
REDIRECT_URI  = os.environ["GITHUB_REDIRECT_URI"]
SCOPE         = "repo,read:user,admin:repo_hook"


@router.get("/login")
async def login(request: Request):
    params = urlencode({
        "client_id":    CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope":        SCOPE,
    })
    return RedirectResponse(f"https://github.com/login/oauth/authorize?{params}")


@router.get("/callback")
async def callback(request: Request):
    code = request.query_params.get("code")
    if not code:
        return RedirectResponse(url="/auth/login")

    async with httpx.AsyncClient() as client:
        # Exchange code for token
        token_resp = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id":     CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "code":          code,
                "redirect_uri":  REDIRECT_URI,
            },
            headers={"Accept": "application/json"},
        )
        token_resp.raise_for_status()
        access_token = token_resp.json().get("access_token")

        if not access_token:
            return RedirectResponse(url="/auth/login")

        # Fetch GitHub profile
        profile_resp = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {access_token}"},
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
    return RedirectResponse(url="/dashboard")


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/")


async def get_current_user(request: Request) -> dict | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    async with get_db() as db:
        return await get_user_by_id(db, user_id)
