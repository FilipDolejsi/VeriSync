import os

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from auth.github_oauth import router as auth_router
from db.store import init_db

app = FastAPI(title="VeriSync")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ["SESSION_SECRET_KEY"],
    session_cookie="verisync_session",
    max_age=28800,  # 8 hours
    https_only=False,  # flip to True in prod
)

app.include_router(auth_router)


@app.on_event("startup")
async def startup():
    await init_db()


@app.get("/")
async def root():
    return {"status": "ok"}
