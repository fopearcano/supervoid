"""User management — admin-governed account lifecycle.

These endpoints sit alongside ``/auth`` (which only issues tokens and reports the
current user). Creating accounts, changing the global ``UserRole``, and
activating / deactivating users are studio-wide administrative actions, so they
are ``ADMIN_ONLY``. Password rotation is the one exception: an admin may rotate
anyone's password and a user may rotate their own.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from app.auth import ADMIN_ONLY, get_current_user
from app.auth.security import hash_password
from app.db import get_session
from app.models import User, UserRole
from app.schemas.user import PasswordRotate, UserCreate, UserRead, UserUpdate
from app.utils import (
    Page,
    PageParams,
    apply_patch,
    get_or_404,
    page_params,
    paginate,
)

router = APIRouter(prefix="/users", tags=["users"])


class UserSortBy(str, Enum):
    FULL_NAME = "full_name"
    EMAIL = "email"
    ROLE = "role"
    CREATED_AT = "created_at"


_SORT_COLUMNS = {
    UserSortBy.FULL_NAME: User.full_name,
    UserSortBy.EMAIL: User.email,
    UserSortBy.ROLE: User.role,
    UserSortBy.CREATED_AT: User.created_at,
}


@router.get("", response_model=Page[UserRead], dependencies=ADMIN_ONLY)
def list_users(
    session: Session = Depends(get_session),
    params: PageParams = Depends(page_params),
    role: Optional[UserRole] = Query(default=None),
    is_active: Optional[bool] = Query(default=None),
    q: Optional[str] = Query(default=None, description="Search name/email"),
    sort_by: UserSortBy = Query(default=UserSortBy.FULL_NAME),
    sort_dir: Literal["asc", "desc"] = Query(default="asc"),
) -> Page[UserRead]:
    stmt = select(User)
    if role is not None:
        stmt = stmt.where(User.role == role)
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)
    if q:
        like = f"%{q}%"
        stmt = stmt.where((User.full_name.ilike(like)) | (User.email.ilike(like)))

    column = _SORT_COLUMNS[sort_by]
    stmt = stmt.order_by(column.desc() if sort_dir == "desc" else column.asc())

    items, total = paginate(session, stmt, params)
    return Page[UserRead](
        items=[UserRead.model_validate(i) for i in items],
        total=total,
        skip=params.skip,
        limit=params.limit,
    )


@router.get("/{user_id}", response_model=UserRead, dependencies=ADMIN_ONLY)
def get_user(user_id: str, session: Session = Depends(get_session)) -> User:
    return get_or_404(session, User, user_id, name="User")


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=ADMIN_ONLY,
)
def create_user(
    payload: UserCreate, session: Session = Depends(get_session)
) -> User:
    existing = session.exec(select(User).where(User.email == payload.email)).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        role=payload.role,
        is_active=payload.is_active,
        hashed_password=hash_password(payload.password),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserRead, dependencies=ADMIN_ONLY)
def update_user(
    user_id: str,
    payload: UserUpdate,
    session: Session = Depends(get_session),
) -> User:
    user = get_or_404(session, User, user_id, name="User")
    if payload.email is not None and payload.email != user.email:
        clash = session.exec(
            select(User).where(User.email == payload.email)
        ).first()
        if clash is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )
    apply_patch(user, payload)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@router.post("/{user_id}/activate", response_model=UserRead, dependencies=ADMIN_ONLY)
def activate_user(user_id: str, session: Session = Depends(get_session)) -> User:
    user = get_or_404(session, User, user_id, name="User")
    user.is_active = True
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@router.post("/{user_id}/deactivate", response_model=UserRead, dependencies=ADMIN_ONLY)
def deactivate_user(
    user_id: str,
    session: Session = Depends(get_session),
    actor: User = Depends(get_current_user),
) -> User:
    if user_id == actor.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own account",
        )
    user = get_or_404(session, User, user_id, name="User")
    user.is_active = False
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@router.post("/{user_id}/rotate-password", response_model=UserRead)
def rotate_password(
    user_id: str,
    payload: PasswordRotate,
    session: Session = Depends(get_session),
    actor: User = Depends(get_current_user),
) -> User:
    """Admins may rotate any password; a user may rotate their own."""
    if actor.role != UserRole.ADMIN and actor.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not permitted to rotate this password",
        )
    user = get_or_404(session, User, user_id, name="User")
    user.hashed_password = hash_password(payload.new_password)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
