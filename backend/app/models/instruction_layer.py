"""The Brain's stable instruction layer — versioned, governed records.

Five versioned record families, each a parent + append-only version child
(mirroring ``PromptTemplate`` / ``PromptTemplateVersion``): the **Studio
Constitution**, **assistant profiles**, **context templates**, the
**safety/approval policy**, and the **terminology glossary**. The parent holds
a ``current_version`` pointer and a stable ``key``; all mutable content lives in
the version rows so every change is an immutable new version (the
``ContextAssembler`` stamps the active versions into every request, and the
prompt-prefix cache invalidates when a version changes).

No field ever stores a model secret, API key or credential — ``model_preference``
holds only a model identifier.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, Relationship

from app.models.base import BaseEntity
from app.models.enums import SafetyApprovalMode


# --- Studio Constitution ---------------------------------------------------
class StudioConstitution(BaseEntity, table=True):
    """The studio's standing instructions (a singleton, ``key='studio-constitution'``)."""

    __tablename__ = "studio_constitutions"

    key: str = Field(max_length=120, unique=True, index=True)
    name: str = Field(max_length=200)
    description: Optional[str] = Field(default=None)
    current_version: int = Field(default=1)
    enabled: bool = Field(default=True, index=True)

    versions: list["StudioConstitutionVersion"] = Relationship(
        back_populates="constitution",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class StudioConstitutionVersion(BaseEntity, table=True):
    __tablename__ = "studio_constitution_versions"

    constitution_id: str = Field(foreign_key="studio_constitutions.id", index=True)
    version: int = Field(default=1, index=True)
    body: str = Field(default="")
    notes: Optional[str] = Field(default=None)
    created_by_id: Optional[str] = Field(default=None, foreign_key="users.id", index=True)

    constitution: "StudioConstitution" = Relationship(back_populates="versions")


# --- Assistant profiles ----------------------------------------------------
class AssistantProfile(BaseEntity, table=True):
    """A named assistant persona. ``key`` is the stable handle stored in
    ``BrainConversation.active_profile``; all content is versioned."""

    __tablename__ = "assistant_profiles"

    key: str = Field(max_length=80, unique=True, index=True)
    name: str = Field(max_length=200)
    description: Optional[str] = Field(default=None)
    current_version: int = Field(default=1)
    enabled: bool = Field(default=True, index=True)

    versions: list["AssistantProfileVersion"] = Relationship(
        back_populates="profile",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class AssistantProfileVersion(BaseEntity, table=True):
    # ``model_preference`` lives in Pydantic's protected ``model_`` namespace.
    model_config = {"protected_namespaces": ()}

    __tablename__ = "assistant_profile_versions"

    profile_id: str = Field(foreign_key="assistant_profiles.id", index=True)
    version: int = Field(default=1, index=True)

    purpose: str = Field(default="")
    permitted_domains: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    required_project_scope: bool = Field(default=True)
    # OpenAI-style tool schemas passed straight to ``ChatRequest.tools``.
    available_tools: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    tone: str = Field(default="")
    response_format: str = Field(default="prose", max_length=60)
    approval_policy: str = Field(default="default", max_length=120)  # SafetyApprovalPolicy.key
    default_temperature: float = Field(default=0.3, ge=0, le=2)
    output_limit: int = Field(default=1500, ge=1)
    # A model identifier only (never a key); None / "inherit" => provider default.
    model_preference: Optional[str] = Field(default=None, max_length=160)
    # PermissionScope values that gate this profile's permitted domains.
    required_scopes: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    notes: Optional[str] = Field(default=None)
    created_by_id: Optional[str] = Field(default=None, foreign_key="users.id", index=True)

    profile: "AssistantProfile" = Relationship(back_populates="versions")


# --- Context templates (segment framing) -----------------------------------
class ContextTemplate(BaseEntity, table=True):
    """Static framing text for a context segment (e.g. the untrusted-evidence
    delimiter, the tool-policy preamble). Versioned so prefix bytes are stable."""

    __tablename__ = "context_templates"

    key: str = Field(max_length=120, unique=True, index=True)
    name: str = Field(max_length=200)
    description: Optional[str] = Field(default=None)
    current_version: int = Field(default=1)
    enabled: bool = Field(default=True, index=True)

    versions: list["ContextTemplateVersion"] = Relationship(
        back_populates="template",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class ContextTemplateVersion(BaseEntity, table=True):
    __tablename__ = "context_template_versions"

    template_id: str = Field(foreign_key="context_templates.id", index=True)
    version: int = Field(default=1, index=True)
    segment_key: str = Field(default="", max_length=60, index=True)
    body: str = Field(default="")
    notes: Optional[str] = Field(default=None)
    created_by_id: Optional[str] = Field(default=None, foreign_key="users.id", index=True)

    template: "ContextTemplate" = Relationship(back_populates="versions")


# --- Safety / approval policy ----------------------------------------------
class SafetyApprovalPolicy(BaseEntity, table=True):
    __tablename__ = "safety_approval_policies"

    key: str = Field(max_length=120, unique=True, index=True)
    name: str = Field(max_length=200)
    description: Optional[str] = Field(default=None)
    current_version: int = Field(default=1)
    enabled: bool = Field(default=True, index=True)

    versions: list["SafetyApprovalPolicyVersion"] = Relationship(
        back_populates="policy",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class SafetyApprovalPolicyVersion(BaseEntity, table=True):
    __tablename__ = "safety_approval_policy_versions"

    policy_id: str = Field(foreign_key="safety_approval_policies.id", index=True)
    version: int = Field(default=1, index=True)
    mode: SafetyApprovalMode = Field(default=SafetyApprovalMode.AUTO, index=True)
    # PermissionScope name required to act under this policy (e.g. APPROVE).
    required_scope_to_act: Optional[str] = Field(default=None, max_length=60)
    blocked_tools: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    rules: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    notes: Optional[str] = Field(default=None)
    created_by_id: Optional[str] = Field(default=None, foreign_key="users.id", index=True)

    policy: "SafetyApprovalPolicy" = Relationship(back_populates="versions")


# --- Terminology glossary --------------------------------------------------
class TerminologyGlossary(BaseEntity, table=True):
    __tablename__ = "terminology_glossaries"

    key: str = Field(max_length=120, unique=True, index=True)
    name: str = Field(max_length=200)
    description: Optional[str] = Field(default=None)
    current_version: int = Field(default=1)
    enabled: bool = Field(default=True, index=True)

    versions: list["TerminologyGlossaryVersion"] = Relationship(
        back_populates="glossary",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class TerminologyGlossaryVersion(BaseEntity, table=True):
    __tablename__ = "terminology_glossary_versions"

    glossary_id: str = Field(foreign_key="terminology_glossaries.id", index=True)
    version: int = Field(default=1, index=True)
    # [{term, definition, aliases:[...]}] — kept sorted by term for stable bytes.
    entries: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    body: str = Field(default="")  # rendered, term-sorted glossary text
    notes: Optional[str] = Field(default=None)
    created_by_id: Optional[str] = Field(default=None, foreign_key="users.id", index=True)

    glossary: "TerminologyGlossary" = Relationship(back_populates="versions")
