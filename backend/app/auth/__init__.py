"""Authentication primitives: hashing, JWT, dependencies."""

from app.auth.dependencies import (
    ADMIN_ONLY,
    AUTHED,
    BRAIN_AUTHED,
    BrainPrincipal,
    get_brain_principal,
    get_current_user,
    oauth2_scheme,
    require_role,
)
from app.auth.security import (
    create_access_token,
    decode_token,
    generate_brain_token,
    hash_brain_token,
    hash_password,
    verify_password,
)

__all__ = [
    "ADMIN_ONLY",
    "AUTHED",
    "BRAIN_AUTHED",
    "BrainPrincipal",
    "create_access_token",
    "decode_token",
    "generate_brain_token",
    "get_brain_principal",
    "get_current_user",
    "hash_brain_token",
    "hash_password",
    "oauth2_scheme",
    "require_role",
    "verify_password",
]
