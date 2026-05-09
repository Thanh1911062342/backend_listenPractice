from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class UserRegister(BaseModel):
    username: str
    email: Optional[str] = None
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    email: Optional[str]
    is_active: bool
    is_admin: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
