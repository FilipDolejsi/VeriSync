import os

from dotenv import load_dotenv
load_dotenv()

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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

# frontend_origin = os.environ.get("https://veri-sync.lovable.app", "http://localhost:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://veri-sync.lovable.app",
        "https://id-preview--68091988-a492-4c0e-b25b-f2cab9f40249.lovable.app",
        "https://68091988-a492-4c0e-b25b-f2cab9f40249.lovable.app",
        "https://68091988-a492-4c0e-b25b-f2cab9f40249.lovableproject.com",  # editor iframe
        "http://localhost:5173",  # local dev
        "http://localhost:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ["SESSION_SECRET_KEY"],
    session_cookie="verisync_session",
    max_age=28800,
    https_only=True,        # REQUIRED on Render (HTTPS)
    same_site="none",       # REQUIRED for cross-site cookies
)


app.include_router(auth_router)
app.include_router(webhook_router)
app.include_router(events_router)
app.include_router(dashboard_router)


@app.get("/")
async def root():
    return {"status": "ok"}
