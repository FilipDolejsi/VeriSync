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
        "https://veri-sync.lovable.app",                                              # published
        "https://id-preview--68091988-a492-4c0e-b25b-f2cab9f40249.lovable.app",      # preview
        "https://68091988-a492-4c0e-b25b-f2cab9f40249.lovable.app",                  # project URL
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
    https_only=False,  # flip to True in prod
)

app.include_router(auth_router)
app.include_router(webhook_router)
app.include_router(events_router)
app.include_router(dashboard_router)


@app.get("/")
async def root():
    return {"status": "ok"}
