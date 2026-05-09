from sqlalchemy.orm import Session

from app.modules.auth.model import User


def get_by_id(db: Session, user_id: int) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def get_by_username(db: Session, username: str) -> User | None:
    return db.query(User).filter(User.username == username).first()


def get_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()


def create(db: Session, username: str, email: str | None, password_hash: str) -> User:
    user = User(username=username, email=email, password_hash=password_hash)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
