from __future__ import annotations

from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    EDITOR = "editor"
    REVIEWER = "reviewer"
    PRODUCTION_MANAGER = "production_manager"
    MARKETING = "marketing"
    ARCHIVE_READER = "archive_reader"


class WorkType(str, Enum):
    """The publication format a manuscript is destined to become.

    Distinguishes the publishing house's principal product lines — long-form
    books and graphic novels — alongside the other editorial formats a press
    handles. The workflow and production pipeline are shared across all types.
    """

    BOOK = "book"
    GRAPHIC_NOVEL = "graphic_novel"
    NOVELLA = "novella"
    ANTHOLOGY = "anthology"
    ART_BOOK = "art_book"
    ESSAY = "essay"
    ADAPTATION_CANDIDATE = "adaptation_candidate"
    OTHER = "other"


class WorkflowStatus(str, Enum):
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DEVELOPMENT_EDITING = "development_editing"
    COPY_EDITING = "copy_editing"
    PROOFREADING = "proofreading"
    LAYOUT = "layout"
    COVER_DESIGN = "cover_design"
    PREPRESS = "prepress"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ReviewVerdict(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    REVISE = "revise"
    HOLD = "hold"


class ContractStatus(str, Enum):
    DRAFT = "draft"
    SENT = "sent"
    SIGNED = "signed"
    TERMINATED = "terminated"


class ProductionStage(str, Enum):
    LAYOUT = "layout"
    COVER_DESIGN = "cover_design"
    PREPRESS = "prepress"
    PRINTING = "printing"


class ProductionItemStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"


class EditorialNoteKind(str, Enum):
    GENERAL = "general"
    STRUCTURAL = "structural"
    LINE = "line"
    DESIGN = "design"
    PRODUCTION = "production"


class StreamStatus(str, Enum):
    """Status of a single production stream (format or stage)."""

    NOT_PLANNED = "not_planned"
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETE = "complete"


class AttachmentKind(str, Enum):
    """Categories of file attached to a manuscript."""

    MANUSCRIPT_DRAFT = "manuscript_draft"
    EDITOR_MARKED_COPY = "editor_marked_copy"
    COVER_ARTWORK = "cover_artwork"
    PROOF = "proof"
    CONTRACT_SCAN = "contract_scan"
    OTHER = "other"


class ExportFormat(str, Enum):
    """Available manuscript export formats."""

    MARKDOWN = "markdown"
    JSON = "json"
    PDF = "pdf"  # registered placeholder — implementation pending


class AIFeature(str, Enum):
    """The editorial AI features exposed at /api/ai/manuscripts/..."""

    SUMMARIZE = "summarize"
    STYLE_ANALYSIS = "style_analysis"
    EDITORIAL_SUGGESTIONS = "editorial_suggestions"
    SEMANTIC_TAGS = "semantic_tags"
    CONSISTENCY_CHECK = "consistency_check"


class EntityKind(str, Enum):
    """Kinds of node in the editorial knowledge graph."""

    CHARACTER = "character"
    PLACE = "place"
    THEME = "theme"
    MOTIF = "motif"
    ORGANIZATION = "organization"
    WORK = "work"
    PERSON = "person"
    PERIOD = "period"
    OTHER = "other"


class RelationshipKind(str, Enum):
    """Typed edges between knowledge entities."""

    RELATED_TO = "related_to"
    INFLUENCES = "influences"
    DESCENDS_FROM = "descends_from"
    CONTRASTS_WITH = "contrasts_with"
    INHABITS = "inhabits"
    AUTHORED = "authored"
    PART_OF = "part_of"
    SIBLING_OF = "sibling_of"
    MENTOR_OF = "mentor_of"
    ADAPTS = "adapts"
    OTHER = "other"


class ManuscriptLinkRole(str, Enum):
    """How a manuscript relates to a knowledge entity."""

    TAGGED = "tagged"
    FEATURES = "features"
    REFERENCES = "references"
    SET_IN = "set_in"
    DERIVED_FROM = "derived_from"
    OTHER = "other"


class WorkStatus(str, Enum):
    """Lifecycle of a Work (the publishing project), distinct from the
    manuscript-level editorial workflow.

    A Work is the central catalogue entity; its status tracks where the
    project sits across acquisition, production and release.
    """

    CONCEPT = "concept"
    PLANNED = "planned"
    IN_DEVELOPMENT = "in_development"
    IN_PRODUCTION = "in_production"
    PUBLISHED = "published"
    ON_HOLD = "on_hold"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


class DraftStatus(str, Enum):
    """Maturity of a specific manuscript draft/version."""

    OUTLINE = "outline"
    FIRST_DRAFT = "first_draft"
    REVISED_DRAFT = "revised_draft"
    FINAL_DRAFT = "final_draft"
    DELIVERED = "delivered"


class RightStatus(str, Enum):
    """Status of an individual right within a rights profile."""

    AVAILABLE = "available"  # open to license
    RESERVED = "reserved"  # held back, not offered
    OPTIONED = "optioned"  # under option, not yet licensed
    LICENSED = "licensed"  # licensed to a third party
    SOLD = "sold"  # outright sale / assigned
    NOT_APPLICABLE = "not_applicable"


class CalendarEventType(str, Enum):
    """Categories of entry on the publishing calendar."""

    ANNOUNCEMENT = "announcement"
    COVER_REVEAL = "cover_reveal"
    PREORDER = "preorder"
    RELEASE = "release"
    REPRINT = "reprint"
    LAUNCH_EVENT = "launch_event"
    SIGNING = "signing"
    OTHER = "other"


class CalendarEventStatus(str, Enum):
    """Lifecycle of a publishing calendar entry."""

    PLANNED = "planned"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class IntegrationPointType(str, Enum):
    """The ecosystem system a persisted integration point targets."""

    LOGOSFORGE = "logosforge"  # the separate writing/narrative subsystem
    SUPERVOID_MOVIES = "supervoid_movies"  # future screen-adaptation division
    AI_LAB = "ai_lab"
    ARCHIVE_KNOWLEDGE_GRAPH = "archive_knowledge_graph"
    OTHER = "other"


class IntegrationPointStatus(str, Enum):
    """Operational status of a persisted integration point."""

    PLANNED = "planned"
    ACTIVE = "active"
    DISABLED = "disabled"


# --- Public Graphic Novel Webviewer ----------------------------------------
# These back the *public* reader projection only. They are deliberately kept
# separate from the private editorial enums above so nothing internal leaks
# into the public-facing layer.


class PublishedStatus(str, Enum):
    """Visibility of a published-reader record.

    Only ``PUBLISHED`` titles are listed publicly; ``UNLISTED`` is reachable
    by direct slug but not enumerated; ``DRAFT`` / ``ARCHIVED`` are hidden.
    """

    DRAFT = "draft"
    PUBLISHED = "published"
    UNLISTED = "unlisted"
    ARCHIVED = "archived"


class MediaAssetType(str, Enum):
    """Kind of public media asset referenced by the reader."""

    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"


class HotspotType(str, Enum):
    """Curated, public-only interactive hotspot kinds."""

    INFO = "info"
    CHARACTER = "character"
    LOCATION = "location"
    LORE = "lore"
    EXTERNAL_LINK = "external_link"
    AUDIO = "audio"
    VIDEO = "video"


# --- IP / transmedia studio layer (above Work) -----------------------------
# These turn the catalogue into an IP-centred transmedia studio. Work remains
# the central production/catalogue entity; these sit above and around it.


class StudioDivision(str, Enum):
    """A creative division of the studio (the medium family a Work belongs to)."""

    PUBLISHING = "publishing"
    PICTURES = "pictures"
    INTERACTIVE = "interactive"
    AUDIO = "audio"
    CROSS_MEDIA = "cross_media"


class Medium(str, Enum):
    """A concrete delivery medium for a Work or an adaptation target."""

    BOOK = "book"
    GRAPHIC_NOVEL = "graphic_novel"
    FILM = "film"
    SHORT_FILM = "short_film"
    SERIES = "series"
    ANIMATION = "animation"
    AUDIO_DRAMA = "audio_drama"
    WEB_EXPERIENCE = "web_experience"
    GAME = "game"
    OTHER = "other"


class CanonState(str, Enum):
    """How a Work stands relative to its story world's canon."""

    CANON = "canon"
    SOFT_CANON = "soft_canon"
    ALTERNATE = "alternate"
    NON_CANON = "non_canon"
    UNDECIDED = "undecided"


class AdaptationStatus(str, Enum):
    """Lifecycle of an adaptation dossier."""

    PROPOSED = "proposed"
    OPTIONED = "optioned"
    IN_DEVELOPMENT = "in_development"
    IN_PRODUCTION = "in_production"
    RELEASED = "released"
    ON_HOLD = "on_hold"
    ABANDONED = "abandoned"


class RightsClearanceState(str, Enum):
    """Rights-clearance state for an adaptation."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    CLEARED = "cleared"
    BLOCKED = "blocked"
    NOT_REQUIRED = "not_required"


class StoryWorldStatus(str, Enum):
    """Lifecycle of a story world / IP."""

    DEVELOPING = "developing"
    ACTIVE = "active"
    DORMANT = "dormant"
    ARCHIVED = "archived"


class StorySeriesStatus(str, Enum):
    """Lifecycle of a series within a story world."""

    PLANNED = "planned"
    ONGOING = "ongoing"
    COMPLETE = "complete"
    ON_HOLD = "on_hold"
    ARCHIVED = "archived"
