"""
dashboard/server.py
───────────────────
FastAPI router that mounts the Jinja2 dashboard pages and the JSON
APIs that feed the History + Analytics views.

Mount in main.py:

    from dashboard.server import router as dashboard_router
    from dashboard.events import router as events_router
    app.include_router(dashboard_router)
    app.include_router(events_router)
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from auth.github_oauth import get_current_user  # type: ignore
from db import store

router = APIRouter()

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Static files (CSS/JS) — mounted on the parent app at /static
# Call once from main.py:
#     app.mount("/static", StaticFiles(directory="dashboard/static"), name="static")


# ─────────────────────────── helpers ──────────────────────────────
def _relative_time(ts: datetime) -> str:
    delta = datetime.utcnow() - ts
    seconds = int(delta.total_seconds())
    if seconds < 60:   return f"{seconds}s ago"
    if seconds < 3600: return f"{seconds // 60}m ago"
    if seconds < 86400:return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def _model_breakdown_summary(breakdown: dict) -> str:
    """ {'gemini-pro': 2, 'mistral-7b': 4} → 'gemini-pro ×2, mistral-7b ×4' """
    return ", ".join(f"{k} ×{v}" for k, v in sorted(breakdown.items(), key=lambda x: -x[1])[:3])


# ─────────────────────────── pages ────────────────────────────────
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_overview(request: Request, user=Depends(get_current_user)):
    spend = await store.get_spend_summary(user.id)
    repos = await store.list_watched_repos(user.id)
    recent = await store.list_recent_prs(user.id, limit=10)

    recent_view = [
        {
            **pr.dict(),
            "relative_time": _relative_time(pr.created_at),
        }
        for pr in recent
    ]

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "spend": spend,
            "repos": repos,
            "recent_prs": recent_view,
        },
    )


@router.get("/dashboard/history", response_class=HTMLResponse)
async def dashboard_history(
    request: Request,
    user=Depends(get_current_user),
    page: int = Query(1, ge=1),
    repo: Optional[str] = None,
    severity: Optional[str] = Query(None, pattern="^(critical|warning|info)?$"),
):
    page_size = 25
    prs, total = await store.list_prs_paginated(
        user_id=user.id,
        page=page,
        page_size=page_size,
        repo=repo,
        severity=severity,
    )
    total_pages = max(1, (total + page_size - 1) // page_size)

    pr_view = [
        {
            **pr.dict(),
            "model_breakdown_summary": _model_breakdown_summary(pr.model_breakdown),
            "created_at": pr.created_at.strftime("%Y-%m-%d %H:%M"),
        }
        for pr in prs
    ]

    return templates.TemplateResponse(
        "history.html",
        {
            "request": request,
            "user": user,
            "prs": pr_view,
            "page": page,
            "total_pages": total_pages,
            "filters": {"repo": repo, "severity": severity},
        },
    )


@router.get("/dashboard/analytics", response_class=HTMLResponse)
async def dashboard_analytics(request: Request, user=Depends(get_current_user)):
    return templates.TemplateResponse(
        "analytics.html",
        {"request": request, "user": user},
    )


# ─────────────────────────── JSON APIs ────────────────────────────
@router.get("/history")
async def api_history(
    user=Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    repo: Optional[str] = None,
    severity: Optional[str] = Query(None, pattern="^(critical|warning|info)?$"),
):
    """Paginated PR history feed (JSON)."""
    prs, total = await store.list_prs_paginated(
        user_id=user.id,
        page=page,
        page_size=page_size,
        repo=repo,
        severity=severity,
    )
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": [
            {
                **pr.dict(),
                "model_breakdown_summary": _model_breakdown_summary(pr.model_breakdown),
            }
            for pr in prs
        ],
    }


@router.get("/analytics/summary")
async def api_analytics_summary(
    user=Depends(get_current_user),
    days: int = Query(30, ge=1, le=180),
):
    """
    Aggregated analytics for the dashboard charts:
      - severity_by_day: daily critical/warning/info counts
      - model_breakdown: per-model calls, findings, critical, total spend
      - category_breakdown: counts per finding category
    """
    since = datetime.utcnow() - timedelta(days=days)

    severity_by_day = await store.severity_counts_by_day(user.id, since=since)
    model_breakdown = await store.model_breakdown(user.id, since=since)
    category_breakdown = await store.category_breakdown(user.id, since=since)

    return JSONResponse(
        {
            "days": days,
            "severity_by_day": severity_by_day,
            "model_breakdown": model_breakdown,
            "category_breakdown": category_breakdown,
        }
    )
