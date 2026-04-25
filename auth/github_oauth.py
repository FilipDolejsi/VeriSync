import os
import uuid
from datetime import datetime, timezone

import httpx
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from db.store import get_db, upsert_user, get_user_by_github_id, get_user_by_id

router = APIRouter()

oauth = OAuth()
oauth.register(
    name="github",
    client_id=os.environ["GITHUB_CLIENT_ID"],
    client_secret=os.environ["GITHUB_CLIENT_SECRET"],
    access_token_url="https://github.com/login/oauth/access_token",
    authorize_url="https://github.com/login/oauth/authorize",
    client_kwargs={"scope": "repo user"},
)


@router.get("/login")
async def login(request: Request):
    redirect_uri = request.url_for("callback")
    return await oauth.github.authorize_redirect(request, redirect_uri)


@router.get("/auth/callback")
async def callback(request: Request):
    token = await oauth.github.authorize_access_token(request)
    access_token = token["access_token"]

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        profile = resp.json()

    github_id = str(profile["id"])
    now = datetime.now(timezone.utc).isoformat()

    async with await get_db() as db:
        existing = await get_user_by_github_id(db, github_id)
        user_id = existing["id"] if existing else str(uuid.uuid4())

        await upsert_user(db, {
            "id": user_id,
            "github_id": github_id,
            "username": profile["login"],
            "avatar_url": profile.get("avatar_url", ""),
            "wallet_id": existing["wallet_id"] if existing else "",
            "sat_balance": existing["sat_balance"] if existing else 0,
            "created_at": existing["created_at"] if existing else now,
            "last_login": now,
        })

    request.session["user_id"] = user_id
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
    async with await get_db() as db:
        return await get_user_by_id(db, user_id)
