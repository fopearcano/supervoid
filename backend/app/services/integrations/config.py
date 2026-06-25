"""Secure configuration for the integration hub.

Rules enforced here:

* secrets live in the **environment**, never in the database — an
  ``IntegrationPoint`` stores only a logical-name → ENV-VAR-NAME mapping
  (``credential_refs``);
* there is **no raw secret retrieval** through the API — only presence
  booleans and masked configuration are ever returned;
* configuration is masked defensively before it leaves the process.
"""
from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Optional

from app.services.agents import redact  # reuse the secret-key scrubber

if TYPE_CHECKING:
    from app.models import IntegrationPoint

# A credential reference must be an ENVIRONMENT VARIABLE NAME, not a value.
# Validated on write so an actual secret can never be stored by mistake.
ENV_VAR_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def is_valid_env_ref(value: str) -> bool:
    return bool(isinstance(value, str) and ENV_VAR_NAME_RE.match(value))


def resolve_secret(point: "IntegrationPoint", logical_name: str) -> Optional[str]:
    """Resolve a secret from the environment via the point's reference map.

    Returns ``None`` if the credential is unreferenced or unset. The value is
    only ever used to make a live call; it is never persisted or returned.
    """
    env_name = (point.credential_refs or {}).get(logical_name)
    if not env_name:
        return None
    return os.environ.get(env_name)


def credential_status(point: "IntegrationPoint") -> dict[str, bool]:
    """Which referenced credentials are actually present in the environment.

    Booleans only — never the secret values, and never the env-var names.
    """
    out: dict[str, bool] = {}
    for logical, env_name in (point.credential_refs or {}).items():
        out[logical] = bool(env_name and os.environ.get(env_name))
    return out


def masked_config(point: "IntegrationPoint") -> dict:
    """Non-secret configuration, with any secret-looking keys masked.

    ``config`` is meant to hold only non-secret settings; masking is a
    defence-in-depth measure in case something sensitive is ever placed there.
    """
    return redact(point.config or {})
