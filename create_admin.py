"""
Run once to create the first admin account.
Usage: python create_admin.py
"""
from app.database import SessionLocal
from app.modules.auth.model import User
from app.modules.auth.service import hash_password

USERNAME = "admin"
PASSWORD = "admin"   # change this
EMAIL = None

db = SessionLocal()
try:
    if db.query(User).filter(User.username == USERNAME).first():
        print(f"User '{USERNAME}' already exists.")
    else:
        user = User(
            username=USERNAME,
            email=EMAIL,
            password_hash=hash_password(PASSWORD),
            is_active=True,
            is_admin=True,
        )
        db.add(user)
        db.commit()
        print(f"Admin '{USERNAME}' created. Password: {PASSWORD}")
finally:
    db.close()
