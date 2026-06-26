"""Schemas for the Brain stable instruction layer + context assembly."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import SafetyApprovalMode


# --- reads -----------------------------------------------------------------
class ConstitutionRead(BaseModel):
    key: str
    name: str
    description: Optional[str] = None
    current_version: int
    body: str


class ProfileRead(BaseModel):
    # ``model_preference`` lives in the protected ``model_`` namespace.
    model_config = ConfigDict(protected_namespaces=())

    key: str
    name: str
    description: Optional[str] = None
    current_version: int
    purpose: str
    permitted_domains: list[str] = []
    required_project_scope: bool = True
    available_tools: list[Any] = []
    tone: str = ""
    response_format: str = "prose"
    approval_policy: str = "default"
    default_temperature: float = 0.3
    output_limit: int = 1500
    model_preference: Optional[str] = None
    required_scopes: list[str] = []


class TemplateRead(BaseModel):
    key: str
    name: str
    current_version: int
    segment_key: str
    body: str


class PolicyRead(BaseModel):
    key: str
    name: str
    current_version: int
    mode: SafetyApprovalMode
    required_scope_to_act: Optional[str] = None
    blocked_tools: list[str] = []


class GlossaryRead(BaseModel):
    key: str
    name: str
    current_version: int
    entries: list[Any] = []
    body: str


class VersionRef(BaseModel):
    version: int
    notes: Optional[str] = None
    created_by_id: Optional[str] = None


# --- version-create bodies (append a new immutable version) ----------------
class ConstitutionVersionCreate(BaseModel):
    body: str
    notes: Optional[str] = None


class ProfileVersionCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    purpose: str
    permitted_domains: list[str] = []
    required_project_scope: bool = True
    available_tools: list[Any] = []
    tone: str = ""
    response_format: str = "prose"
    approval_policy: str = "default"
    default_temperature: float = Field(default=0.3, ge=0, le=2)
    output_limit: int = Field(default=1500, ge=1)
    model_preference: Optional[str] = None
    required_scopes: list[str] = []
    notes: Optional[str] = None


class TemplateVersionCreate(BaseModel):
    segment_key: str
    body: str
    notes: Optional[str] = None


class PolicyVersionCreate(BaseModel):
    mode: SafetyApprovalMode
    required_scope_to_act: Optional[str] = None
    blocked_tools: list[str] = []
    rules: dict = {}
    notes: Optional[str] = None


class GlossaryVersionCreate(BaseModel):
    entries: list[Any] = []
    notes: Optional[str] = None


# --- context assembly ------------------------------------------------------
class AssembleRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model: Optional[str] = None
    include_evidence: bool = False
    question: Optional[str] = None
