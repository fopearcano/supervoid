from typing import Optional

from sqlmodel import Field

from app.models.base import BaseEntity
from app.models.enums import ProductionActivityType, ProductionItemStatus


class ProductionActivity(BaseEntity, table=True):
    """An append-only event in a production task's history.

    Deliberately decoupled (plain id columns, no foreign keys or relationships)
    so the trail is durable even if the task or actor is later removed. This is
    the audit substrate for the production task system.
    """

    __tablename__ = "production_activities"

    task_id: Optional[str] = Field(default=None, index=True)
    actor_id: Optional[str] = Field(default=None, index=True)

    type: ProductionActivityType = Field(index=True)
    field: Optional[str] = Field(default=None, max_length=60)
    from_status: Optional[ProductionItemStatus] = Field(default=None)
    to_status: Optional[ProductionItemStatus] = Field(default=None)
    summary: Optional[str] = Field(default=None, max_length=500)
    detail: Optional[str] = Field(default=None)
