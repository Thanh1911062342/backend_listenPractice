from datetime import datetime, timedelta

import bcrypt
from fastapi import HTTPException, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.modules.auth import repository
from app.modules.auth.schema import Token, UserRegister


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user_id: int) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": str(user_id), "exp": expire},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def decode_token(token: str) -> int:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def register(db: Session, data: UserRegister) -> Token:
    if repository.get_by_username(db, data.username):
        raise HTTPException(status_code=400, detail="Username already taken")
    if data.email and repository.get_by_email(db, data.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    user = repository.create(db, data.username, data.email, hash_password(data.password))
    return Token(access_token=create_access_token(user.id))


def login(db: Session, username: str, password: str) -> Token:
    user = repository.get_by_username(db, username)
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    return Token(access_token=create_access_token(user.id))
