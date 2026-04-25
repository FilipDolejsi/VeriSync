import os

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from auth.github_oauth import router as auth_router

app = FastAPI(title="ReviewMesh")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ["SESSION_SECRET"],
    session_cookie="reviewmesh_session",
    max_age=86400,
    https_only=False,  # flip to True in prod
)

app.include_router(auth_router)


@app.get("/")
async def root():
    return {"status": "ok"}
