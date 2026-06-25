from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.models.enums import (
    IntegrationHealthStatus,
    IntegrationLinkKind,
    IntegrationPointStatus,
    IntegrationPointType,
    IntegrationRunStatus,
)
from app.schemas._common import TimestampedRead
from app.services.integrations.config import is_valid_env_ref


def _validate_credential_refs(value: Optional[dict]) -> Optional[dict]:
    """A credential reference must map a logical name to an ENV VAR NAME, never
    a secret value. Reject anything that does not look like an env-var name."""
    if value is None:
        return value
    for logical, env_name in value.items():
        if not is_valid_env_ref(env_name):
            raise ValueError(
                f"credential_refs['{logical}'] must be an environment variable "
                "name (e.g. SUPERVOID_GITHUB_TOKEN), not a secret value."
            )
    return value


# --- IntegrationPoint CRUD -------------------------------------------------


class IntegrationPointCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: IntegrationPointType = IntegrationPointType.OTHER
    status: IntegrationPointStatus = IntegrationPointStatus.PLANNED
    endpoint: Optional[str] = Field(default=None, max_length=500)
    notes: Optional[str] = None
    adapter_key: Optional[str] = Field(default=None, max_length=120)
    enabled: bool = True
    config: dict = Field(default_factory=dict)
    credential_refs: dict = Field(default_factory=dict)

    _check_refs = field_validator("credential_refs")(_validate_credential_refs)


class IntegrationPointUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    type: Optional[IntegrationPointType] = None
    status: Optional[IntegrationPointStatus] = None
    endpoint: Optional[str] = Field(default=None, max_length=500)
    notes: Optional[str] = None
    adapter_key: Optional[str] = Field(default=None, max_length=120)
    enabled: Optional[bool] = None
    config: Optional[dict] = None
    credential_refs: Optional[dict] = None

    _check_refs = field_validator("credential_refs")(_validate_credential_refs)


class IntegrationPointRead(TimestampedRead):
    name: str
    type: IntegrationPointType
    status: IntegrationPointStatus
    endpoint: Optional[str]
    notes: Optional[str]
    adapter_key: Optional[str]
    enabled: bool
    config: dict
    # credential_refs (env-var names) are deliberately NOT exposed; presence is
    # reported via the dedicated config-status endpoint as booleans only.


# --- Adapter registry ------------------------------------------------------


class AdapterOperationRead(BaseModel):
    key: str
    name: str
    summary: str
    direction: str
    mutating: bool
    external: bool
    touches_network: bool
    requires_approval: bool
    admin_gated: bool
    read_only: bool
    risk: str


class AdapterRead(BaseModel):
    key: str
    kind: str
    name: str
    description: str
    required_config: list[str]
    credential_names: list[str]
    operations: list[AdapterOperationRead]


# --- Health & configuration status -----------------------------------------


class HealthRead(BaseModel):
    status: IntegrationHealthStatus
    detail: str
    configured: bool
    checked_live: bool
    credentials: dict[str, bool]
    missing_config: list[str]


class ConfigStatusRead(BaseModel):
    adapter_key: Optional[str]
    enabled: bool
    config: dict
    credentials: dict[str, bool]
    required_config: list[str]
    missing_config: list[str]


# --- Operations & runs -----------------------------------------------------


class OperationRequest(BaseModel):
    operation: str = Field(min_length=1, max_length=120)
    payload: dict = Field(default_factory=dict)
    dry_run: bool = False


class RunRejectRequest(BaseModel):
    reason: Optional[str] = None


class IntegrationRunRead(TimestampedRead):
    integration_point_id: str
    adapter_key: str
    operation: str
    direction: str
    status: IntegrationRunStatus
    dry_run: bool
    requires_approval: bool
    is_external: bool
    input: dict
    output: dict
    error: Optional[str]
    requested_by_id: Optional[str]
    requested_by_name: Optional[str] = None
    approved_by_id: Optional[str]
    approved_at: Optional[datetime]
    rejected_by_id: Optional[str]
    rejected_at: Optional[datetime]
    approval_proposal_id: Optional[str]
    correlation_id: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


class IntegrationLinkRead(TimestampedRead):
    integration_point_id: str
    external_kind: IntegrationLinkKind
    external_ref: str
    external_url: Optional[str]
    title: Optional[str]
    target_type: str
    target_id: str
    extra: dict
