from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import ApprovalDecision, ApprovalStatus
from app.schemas._common import TimestampedRead


class ApprovalCreate(BaseModel):
    """Request a human approval. Either ``task_id`` (the common case) or a
    generic ``target_type`` + ``target_id`` identifies what is being approved."""

    approver_id: str
    task_id: Optional[str] = None
    target_type: Optional[str] = Field(default=None, max_length=60)
    target_id: Optional[str] = None
    title: Optional[str] = Field(default=None, max_length=300)
    description: Optional[str] = None


class ApprovalDecisionRequest(BaseModel):
    decision: ApprovalDecision
    comments: Optional[str] = None


class ApprovalRead(TimestampedRead):
    requested_by_id: Optional[str]
    requested_by_name: Optional[str] = None
    approver_id: Optional[str]
    approver_name: Optional[str] = None
    task_id: Optional[str]
    target_type: Optional[str]
    target_id: Optional[str]
    title: Optional[str]
    description: Optional[str]
    status: ApprovalStatus
    decision: Optional[ApprovalDecision]
    comments: Optional[str]
    decided_at: Optional[datetime]
