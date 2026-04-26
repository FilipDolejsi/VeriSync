import os
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse

from db.store import get_db, upsert_user, get_user_by_github_id, get_user_by_id
from payments.wallet import get_wallet

router = APIRouter(prefix="/auth")

oauth = OAuth()
oauth.register(
    name="github",
    client_id=os.environ["GITHUB_CLIENT_ID"],
    client_secret=os.environ["GITHUB_CLIENT_SECRET"],
    access_token_url="https://github.com/login/oauth/access_token",
    authorize_url="https://github.com/login/oauth/authorize",
    client_kwargs={"scope": "repo,read:user,admin:repo_hook"},
)


def _is_safe_redirect_target(redirect: str) -> bool:
    if redirect.startswith("/"):
        return True
    parsed = urlparse(redirect)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


@router.get("/login")
async def login(request: Request, redirect: str = Query("/dashboard")):
    if not _is_safe_redirect_target(redirect):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid redirect URL")

    request.session["post_auth_redirect"] = redirect
    redirect_uri = os.environ["GITHUB_REDIRECT_URI"]
    return await oauth.github.authorize_redirect(request, redirect_uri)


@router.get("/callback")
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

    async with get_db() as db:
        existing = await get_user_by_github_id(db, github_id)

        if existing:
            user_id = existing["id"]
            wallet_id = existing["wallet_id"]
        else:
            user_id = str(uuid.uuid4())
            wallet_id = get_wallet().create_wallet(user_id)

        await upsert_user(db, {
            "id": user_id,
            "github_id": github_id,
            "username": profile["login"],
            "avatar_url": profile.get("avatar_url", ""),
            "wallet_id": wallet_id,
            "sat_balance": existing["sat_balance"] if existing else 0,
            "github_token": access_token,
            "created_at": existing["created_at"] if existing else now,
            "last_login": now,
        })

    request.session["user_id"] = user_id
    request.session["github_token"] = access_token
    redirect_url = request.session.pop("post_auth_redirect", "/dashboard")
    if not _is_safe_redirect_target(redirect_url):
        redirect_url = "/dashboard"
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)


@router.get("/me")
async def me(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    return {
        "id": user["id"],
        "login": user.get("username"),
        "name": user.get("username"),
        "avatar_url": user.get("avatar_url"),
    }


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("verisync_session")
    return response


@router.get("/logout")
async def logout_compat(request: Request):
    return await logout(request)


async def get_current_user(request: Request) -> dict | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    async with get_db() as db:
        return await get_user_by_id(db, user_id)
