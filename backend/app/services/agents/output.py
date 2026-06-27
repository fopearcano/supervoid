"""The validated structured output an agent's model must produce (Prompt 9).

The model no longer just decorates a deterministic result — it returns a JSON
document that is parsed and validated with Pydantic into an ``AgentOutputModel``.
``build_response_format`` turns the schema into an OpenAI/vLLM ``response_format``
so a capable backend is constrained to emit conforming JSON; ``parse_output``
validates whatever comes back (capable backend or not).

Malformed / non-conforming output raises ``AgentOutputError`` — the runner treats
that as "the model produced nothing usable" and falls back to the deterministic
validators, never to an unchecked blob.
"""
from __future__ import annotations

import json
from typing import Optional

from pydantic import BaseModel, Field, ValidationError

from app.models.enums import AgentRiskLevel, FindingSeverity


class AgentOutputError(ValueError):
    """The model's output was missing, not JSON, or failed schema validation."""


class ModelEvidenceRef(BaseModel):
    """A machine-readable pointer to the evidence a claim rests on."""

    ref: str = Field(description="An id/locator, e.g. 'manuscript:123' or a span.")
    label: Optional[str] = None
    note: Optional[str] = None


class ModelFinding(BaseModel):
    severity: FindingSeverity = FindingSeverity.INFO
    message: str = ""
    category: Optional[str] = None
    evidence: dict = Field(default_factory=dict)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    target_type: Optional[str] = None
    target_id: Optional[str] = None


class ModelToolCall(BaseModel):
    """A tool the model wants to use. Read-only tools may be executed (governed,
    in a bounded loop); mutation / external tools can only ever become gated
    proposals — the model can never trigger a direct mutation."""

    tool: str = Field(description="The registered tool key.")
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    payload: dict = Field(default_factory=dict)
    reason: str = ""
    # The model MAY suggest a risk level, but the tool registry's level always
    # wins; this is advisory only and never downgrades a gate.
    risk_level: Optional[AgentRiskLevel] = None


class AgentOutputModel(BaseModel):
    """The contract the model fills in. Every field has a safe default so an
    empty-but-valid document parses (the deterministic validators still run)."""

    result: dict = Field(default_factory=dict)
    findings: list[ModelFinding] = Field(default_factory=list)
    proposed_tool_calls: list[ModelToolCall] = Field(default_factory=list)
    evidence_references: list[ModelEvidenceRef] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0, le=1)
    unanswered_questions: list[str] = Field(default_factory=list)


# A refusal document (some backends return {"refusal": "..."}). Detected so the
# runner can record the refusal explicitly rather than mis-reading it as empty.
def is_refusal(raw: dict) -> Optional[str]:
    for key in ("refusal", "error", "decline"):
        val = raw.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def build_response_format() -> dict:
    """The OpenAI/vLLM ``response_format`` for strict JSON-schema output."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "agent_output",
            "schema": AgentOutputModel.model_json_schema(),
            "strict": False,
        },
    }


def schema_hint() -> str:
    """A compact, human-readable description of the required JSON, embedded in the
    system prompt so even a backend without native schema enforcement is steered
    to the right shape."""
    return (
        "Respond with a SINGLE JSON object and nothing else, matching:\n"
        "{\n"
        '  "result": object,                      // synthesis / conclusion\n'
        '  "findings": [ {"severity","message","category","evidence","confidence",'
        '"target_type","target_id"} ],\n'
        '  "proposed_tool_calls": [ {"tool","target_type","target_id","payload","reason"} ],\n'
        '  "evidence_references": [ {"ref","label","note"} ],\n'
        '  "confidence": number 0..1,\n'
        '  "unanswered_questions": [ string ]\n'
        "}\n"
        "Only propose tools from the allowed list. Mutation/external tools become "
        "human-approved proposals; you can never execute them yourself."
    )


def parse_output(content: Optional[str]) -> AgentOutputModel:
    """Parse + validate a raw model response into an ``AgentOutputModel``.
    Raises ``AgentOutputError`` for missing / non-JSON / refusal / schema-invalid
    output."""
    if not content or not content.strip():
        raise AgentOutputError("Model returned an empty response.")
    try:
        raw = json.loads(content)
    except (json.JSONDecodeError, TypeError) as exc:
        raise AgentOutputError(f"Model output was not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise AgentOutputError("Model output was not a JSON object.")
    refusal = is_refusal(raw)
    if refusal is not None:
        raise AgentOutputError(f"Model refused: {refusal}")
    try:
        return AgentOutputModel.model_validate(raw)
    except ValidationError as exc:
        raise AgentOutputError(f"Model output failed schema validation: {exc}") from exc
