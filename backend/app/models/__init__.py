"""Domain models for SUPERVOID Publishing.

Importing this package registers every SQLModel table with the shared
metadata registry, so `init_db()` can materialise them against the
configured database engine.
"""
from app.models.adaptation_dossier import AdaptationDossier
from app.models.ai_insight import AIInsight
from app.models.attachment import Attachment
from app.models.author import Author
from app.models.calendar_event import PublishingCalendarEvent
from app.models.contract import Contract
from app.models.editorial_note import EditorialNote
from app.models.enums import (
    AdaptationStatus,
    AIFeature,
    AttachmentKind,
    CalendarEventStatus,
    CalendarEventType,
    CanonState,
    ContractStatus,
    DraftStatus,
    EditorialNoteKind,
    EntityKind,
    ExportFormat,
    HotspotType,
    IntegrationPointStatus,
    IntegrationPointType,
    ManuscriptLinkRole,
    MediaAssetType,
    Medium,
    ProductionItemStatus,
    ProductionStage,
    PublishedStatus,
    RelationshipKind,
    ReviewVerdict,
    RightsClearanceState,
    RightStatus,
    StorySeriesStatus,
    StoryWorldStatus,
    StreamStatus,
    StudioDivision,
    UserRole,
    WorkflowStatus,
    WorkStatus,
    WorkType,
)
from app.models.graphic_novel_production import GraphicNovelProduction
from app.models.integration_point import IntegrationPoint
from app.models.knowledge_entity import KnowledgeEntity
from app.models.knowledge_relationship import KnowledgeRelationship
from app.models.manuscript import Manuscript
from app.models.manuscript_entity_link import ManuscriptEntityLink
from app.models.production_item import ProductionItem
from app.models.production_record import ProductionRecord
from app.models.public_hotspot import PublicHotspot
from app.models.public_media_asset import PublicMediaAsset
from app.models.published_chapter import PublishedChapter
from app.models.published_page import PublishedPage
from app.models.published_volume import PublishedVolume
from app.models.published_work import PublishedWork
from app.models.review import Review
from app.models.rights import Rights
from app.models.story_series import StorySeries
from app.models.story_world import StoryWorld
from app.models.user import User
from app.models.work import Work
from app.models.workflow_event import WorkflowEvent

__all__ = [
    "AdaptationDossier",
    "AdaptationStatus",
    "AIFeature",
    "AIInsight",
    "Attachment",
    "AttachmentKind",
    "Author",
    "CalendarEventStatus",
    "CalendarEventType",
    "CanonState",
    "DraftStatus",
    "EntityKind",
    "GraphicNovelProduction",
    "HotspotType",
    "IntegrationPoint",
    "IntegrationPointStatus",
    "IntegrationPointType",
    "KnowledgeEntity",
    "KnowledgeRelationship",
    "ManuscriptEntityLink",
    "ManuscriptLinkRole",
    "MediaAssetType",
    "PublicHotspot",
    "PublicMediaAsset",
    "PublishedChapter",
    "PublishedPage",
    "PublishedStatus",
    "PublishedVolume",
    "PublishedWork",
    "PublishingCalendarEvent",
    "RelationshipKind",
    "Contract",
    "ContractStatus",
    "EditorialNote",
    "EditorialNoteKind",
    "ExportFormat",
    "Manuscript",
    "ProductionItem",
    "ProductionItemStatus",
    "ProductionRecord",
    "ProductionStage",
    "Review",
    "ReviewVerdict",
    "Rights",
    "RightStatus",
    "RightsClearanceState",
    "Medium",
    "StudioDivision",
    "StorySeries",
    "StorySeriesStatus",
    "StoryWorld",
    "StoryWorldStatus",
    "StreamStatus",
    "User",
    "UserRole",
    "Work",
    "WorkStatus",
    "WorkflowEvent",
    "WorkflowStatus",
    "WorkType",
]
