from typing import Optional

from sqlmodel import Field

from app.models.base import BaseEntity
from app.models.enums import IntegrationPointStatus, IntegrationPointType


class IntegrationPoint(BaseEntity, table=True):
    """A persisted, editable record of a planned or active integration to a
    sibling SUPERVOID ENTANGLED system.

    This complements the static, code-defined ecosystem descriptors under
    ``app.integrations`` (served read-only at ``/api/integrations``): those
    declare the *contracts*; an ``IntegrationPoint`` is an operational,
    CRUD-able registry entry (e.g. a specific LOGOSFORGE bridge or a
    SUPERVOID Movies adaptation hand-off) with an endpoint placeholder.
    """

    __tablename__ = "integration_points"

    name: str = Field(max_length=200, index=True)
    type: IntegrationPointType = Field(
        default=IntegrationPointType.OTHER, index=True
    )
    status: IntegrationPointStatus = Field(
        default=IntegrationPointStatus.PLANNED, index=True
    )
    endpoint: Optional[str] = Field(default=None, max_length=500)
    notes: Optional[str] = Field(default=None)
