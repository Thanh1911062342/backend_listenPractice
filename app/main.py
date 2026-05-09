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
        "https://listen-practice.vercel.app",
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


@app.on_event("startup")
def seed_admin():
    from app.database import SessionLocal
    from app.modules.auth.model import User
    import bcrypt
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            pw = bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode()
            db.add(User(username="admin", password_hash=pw, is_admin=True))
            db.commit()
            logging.getLogger(__name__).info("Seeded default admin user")
    finally:
        db.close()


@app.get("/api/health")
def health():
    return {"status": "ok"}
