from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import UserRole
from app.schemas._common import TimestampedRead


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=200)
    role: UserRole = UserRole.EDITOR
    is_active: bool = True


class UserUpdate(BaseModel):
    """Patch a user's profile / global role. Password changes go through the
    dedicated rotate-password endpoint, never here."""

    email: Optional[str] = Field(default=None, min_length=3, max_length=255)
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class UserRead(TimestampedRead):
    email: str
    full_name: str
    role: UserRole
    is_active: bool


class PasswordRotate(BaseModel):
    new_password: str = Field(min_length=8, max_length=200)
