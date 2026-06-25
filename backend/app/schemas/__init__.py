"""Pydantic schemas used for request/response payloads."""

from app.schemas.attachment import (
    AttachmentPlaceholderCreate,
    AttachmentRead,
    AttachmentUpdate,
)
from app.schemas.auth import CurrentUserRead, TokenResponse
from app.schemas.author import AuthorCreate, AuthorRead, AuthorUpdate
from app.schemas.calendar_event import (
    PublishingCalendarEventCreate,
    PublishingCalendarEventRead,
    PublishingCalendarEventUpdate,
)
from app.schemas.contract import ContractCreate, ContractRead, ContractUpdate
from app.schemas.editorial_note import (
    EditorialNoteCreate,
    EditorialNoteRead,
    EditorialNoteUpdate,
)
from app.schemas.graphic_novel_production import (
    GraphicNovelProductionCreate,
    GraphicNovelProductionRead,
    GraphicNovelProductionUpdate,
)
from app.schemas.integration_point import (
    IntegrationPointCreate,
    IntegrationPointRead,
    IntegrationPointUpdate,
)
from app.schemas.knowledge import (
    KnowledgeEntityCreate,
    KnowledgeEntityRead,
    KnowledgeEntityUpdate,
    KnowledgeRelationshipCreate,
    KnowledgeRelationshipDetail,
    KnowledgeRelationshipRead,
    KnowledgeRelationshipUpdate,
    ManuscriptEntityLinkCreate,
    ManuscriptEntityLinkRead,
    ManuscriptEntityLinkUpdate,
    NeighborhoodEdge,
    NeighborhoodNode,
    NeighborhoodResult,
)
from app.schemas.manuscript import ManuscriptCreate, ManuscriptRead, ManuscriptUpdate
from app.schemas.membership_audit import MembershipAuditRead, ScopeCatalogEntry
from app.schemas.project_membership import (
    MyProjectRead,
    ProjectMembershipCreate,
    ProjectMembershipRead,
    ProjectMembershipRoleUpdate,
)
from app.schemas.approval_request import (
    ApprovalCreate,
    ApprovalDecisionRequest,
    ApprovalRead,
)
from app.schemas.production_item import (
    ProductionItemCreate,
    ProductionItemRead,
    ProductionItemUpdate,
)
from app.schemas.production_milestone import (
    MilestoneCreate,
    MilestoneRead,
    MilestoneUpdate,
)
from app.schemas.production_record import (
    ProductionRecordCreate,
    ProductionRecordDetail,
    ProductionRecordRead,
    ProductionRecordUpdate,
)
from app.schemas.production_task import (
    DependencyCreate,
    DependencyRead,
    ProductionActivityRead,
    ProductionTaskCreate,
    ProductionTaskDetail,
    ProductionTaskRead,
    ProductionTaskUpdate,
    StatusTransitionRequest,
)
from app.schemas.production_template import (
    ApplyTemplateRequest,
    ApplyTemplateResult,
    ProductionTemplateRead,
)
from app.schemas.review import ReviewCreate, ReviewRead, ReviewUpdate
from app.schemas.rights import RightsCreate, RightsRead, RightsUpdate
from app.schemas.user import PasswordRotate, UserCreate, UserRead, UserUpdate
from app.schemas.work import WorkCreate, WorkRead, WorkUpdate
from app.schemas.workflow_event import (
    TransitionRequest,
    TransitionResponse,
    WorkflowEventCreate,
    WorkflowEventRead,
    WorkflowEventUpdate,
)

__all__ = [
    "AttachmentPlaceholderCreate",
    "AttachmentRead",
    "AttachmentUpdate",
    "AuthorCreate",
    "AuthorRead",
    "AuthorUpdate",
    "CurrentUserRead",
    "TokenResponse",
    "ContractCreate",
    "ContractRead",
    "ContractUpdate",
    "EditorialNoteCreate",
    "EditorialNoteRead",
    "EditorialNoteUpdate",
    "GraphicNovelProductionCreate",
    "GraphicNovelProductionRead",
    "GraphicNovelProductionUpdate",
    "IntegrationPointCreate",
    "IntegrationPointRead",
    "IntegrationPointUpdate",
    "KnowledgeEntityCreate",
    "KnowledgeEntityRead",
    "KnowledgeEntityUpdate",
    "KnowledgeRelationshipCreate",
    "KnowledgeRelationshipDetail",
    "KnowledgeRelationshipRead",
    "KnowledgeRelationshipUpdate",
    "ManuscriptEntityLinkCreate",
    "ManuscriptEntityLinkRead",
    "ManuscriptEntityLinkUpdate",
    "NeighborhoodEdge",
    "NeighborhoodNode",
    "NeighborhoodResult",
    "ManuscriptCreate",
    "ManuscriptRead",
    "ManuscriptUpdate",
    "MembershipAuditRead",
    "MyProjectRead",
    "ProjectMembershipCreate",
    "ProjectMembershipRead",
    "ProjectMembershipRoleUpdate",
    "ScopeCatalogEntry",
    "ApprovalCreate",
    "ApprovalDecisionRequest",
    "ApprovalRead",
    "ApplyTemplateRequest",
    "ApplyTemplateResult",
    "DependencyCreate",
    "DependencyRead",
    "MilestoneCreate",
    "MilestoneRead",
    "MilestoneUpdate",
    "ProductionActivityRead",
    "ProductionItemCreate",
    "ProductionItemRead",
    "ProductionItemUpdate",
    "ProductionTaskCreate",
    "ProductionTaskDetail",
    "ProductionTaskRead",
    "ProductionTaskUpdate",
    "ProductionTemplateRead",
    "StatusTransitionRequest",
    "ProductionRecordCreate",
    "ProductionRecordDetail",
    "ProductionRecordRead",
    "ProductionRecordUpdate",
    "PublishingCalendarEventCreate",
    "PublishingCalendarEventRead",
    "PublishingCalendarEventUpdate",
    "ReviewCreate",
    "ReviewRead",
    "ReviewUpdate",
    "RightsCreate",
    "RightsRead",
    "RightsUpdate",
    "PasswordRotate",
    "UserCreate",
    "UserRead",
    "UserUpdate",
    "TransitionRequest",
    "TransitionResponse",
    "WorkCreate",
    "WorkRead",
    "WorkUpdate",
    "WorkflowEventCreate",
    "WorkflowEventRead",
    "WorkflowEventUpdate",
]
