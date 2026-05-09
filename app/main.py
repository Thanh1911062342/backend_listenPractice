import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

from app.modules.auth.router import router as auth_router
from app.modules.content.router import router as content_router
from app.modules.exercise.router import router as exercise_router
from app.modules.session.router import router as session_router

app = FastAPI(title="Listening Practice API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://frontend-user-listen-practice.vercel.app",
        "http://localhost:3000",
        "http://localhost:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router,     prefix="/api")
app.include_router(content_router,  prefix="/api")
app.include_router(exercise_router, prefix="/api")
app.include_router(session_router,  prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}
