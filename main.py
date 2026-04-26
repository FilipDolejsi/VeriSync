import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from auth.github_oauth import router as auth_router
from gh.webhook import router as webhook_router
from dashboard.events import router as events_router
from dashboard.server import router as dashboard_router
from db.store import init_db
from registry.loader import load_registry
from workers.factory import create_worker_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    registry = load_registry()
    worker_router = create_worker_router(registry)
    app.include_router(worker_router)
    yield


app = FastAPI(title="VeriSync", lifespan=lifespan)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ["SESSION_SECRET_KEY"],
    session_cookie="verisync_session",
    max_age=28800,
    https_only=os.environ.get("HTTPS_ONLY", "true").lower() == "true",
    same_site="lax",  # same-domain: lax is correct and more secure than none
)

app.include_router(dashboard_router)
app.include_router(auth_router)
app.include_router(webhook_router)
app.include_router(events_router)

# Serve static assets (nav.js, css, etc.)
_static = Path("dashboard/static")
if _static.exists():
    app.mount("/static", StaticFiles(directory=_static), name="static")
