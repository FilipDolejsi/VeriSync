"""
Dashboard API routes: reputation leaderboard, analytics, and history.

Endpoints:
    GET  /api/reputation          — sorted leaderboard of all models
    GET  /api/analytics           — spend/finding/router stats for current user
    GET  /api/history             — PR history for current user
    GET  /dashboard               — serve the dashboard SPA
"""

import os

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter()

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")


# ── Auth helper ────────────────────────────────────────────────────────────────

async def _require_user(request: Request) -> dict | None:
    from auth.github_oauth import get_current_user
    return await get_current_user(request)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def dashboard_page():
    path = os.path.join(_TEMPLATE_DIR, "dashboard.html")
    if os.path.exists(path):
        return FileResponse(path, media_type="text/html")
    return JSONResponse({"error": "dashboard.html not found"}, status_code=404)


@router.get("/api/reputation")
async def get_reputation():
    """Return reputation leaderboard for all models, sorted by effective_cost ascending."""
    from db.store import get_all_model_reputations
    from registry.loader import load_registry

    registry = load_registry()
    cost_map = {m.id: m.cost_sats for m in registry}

    reputations = await get_all_model_reputations()

    # Fill in models from the registry that have no episode history yet
    known = {r["model_id"] for r in reputations}
    for model in registry:
        if model.id not in known:
            reputations.append({
                "model_id":        model.id,
                "total_reviews":   0,
                "pass_rate":       0.5,
                "avg_cost_sats":   float(model.cost_sats),
                "avg_findings":    0.0,
                "effective_cost":  float(model.cost_sats),
                "reputation_score": 0.5,
            })

    reputations.sort(key=lambda r: r["effective_cost"])

    # Annotate with display name and star rating
    name_map = {m.id: m.name for m in registry}
    for r in reputations:
        r["name"]  = name_map.get(r["model_id"], r["model_id"])
        r["stars"] = round(r["reputation_score"] * 5, 1)  # 0.0 – 5.0 stars

    return JSONResponse(reputations)


@router.get("/api/analytics")
async def get_analytics(request: Request):
    """Return spend/findings/router stats. Falls back to all users when unauthenticated."""
    from db.store import get_analytics

    user = await _require_user(request)
    user_id = user["id"] if user else "seed-user"  # fallback for demo

    data = await get_analytics(user_id)

    # Merge in up-to-date router stats
    try:
        from router.router import get_router_stats
        data["router"] = get_router_stats()
    except Exception:
        pass

    return JSONResponse(data)


@router.get("/api/history")
async def get_history(request: Request):
    """Return the PR review history for the current user."""
    from db.store import get_user_history

    user = await _require_user(request)
    user_id = user["id"] if user else "seed-user"

    history = await get_user_history(user_id)
    return JSONResponse(history)
