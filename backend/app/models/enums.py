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
    # --- Original states (kept for backward compatibility) ---
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    # --- Extended task-system states ---
    TODO = "todo"
    IN_REVIEW = "in_review"
    CHANGES_REQUESTED = "changes_requested"
    APPROVED = "approved"
    CANCELLED = "cancelled"


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


# --- Collaboration: project-scoped access control --------------------------
# These sit ALONGSIDE the global UserRole (which is unchanged). A user's global
# role still governs studio-wide/admin actions; project membership governs
# access to a specific Work or StoryWorld.


class ProjectRole(str, Enum):
    """A collaborator's role on a specific project (Work or StoryWorld)."""

    OWNER = "owner"
    DIRECTOR = "director"
    EDITOR = "editor"
    WRITER = "writer"
    ARTIST = "artist"
    LETTERER = "letterer"
    COLOURIST = "colourist"
    ANIMATOR = "animator"
    SOUND_DESIGNER = "sound_designer"
    TECHNICIAN = "technician"
    PRODUCTION_MANAGER = "production_manager"
    MARKETING = "marketing"
    REVIEWER = "reviewer"
    VIEWER = "viewer"


class MembershipStatus(str, Enum):
    """Lifecycle of a project membership."""

    INVITED = "invited"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DECLINED = "declined"
    REVOKED = "revoked"


class PermissionScope(str, Enum):
    """A protected operation the policy service can authorise on a project."""

    VIEW_PROJECT = "view_project"
    EDIT_NARRATIVE = "edit_narrative"
    EDIT_VISUAL_ASSETS = "edit_visual_assets"
    MANAGE_PRODUCTION = "manage_production"
    UPLOAD_ASSETS = "upload_assets"
    REVIEW = "review"
    APPROVE = "approve"
    MANAGE_COLLABORATORS = "manage_collaborators"
    PUBLISH = "publish"
    MANAGE_RIGHTS = "manage_rights"
    MANAGE_MARKETING = "manage_marketing"


class MembershipAuditAction(str, Enum):
    """An auditable change to a project membership."""

    INVITED = "invited"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    ROLE_CHANGED = "role_changed"
    SUSPENDED = "suspended"
    REACTIVATED = "reactivated"
    REVOKED = "revoked"


# --- General production task system ----------------------------------------
# The ProductionItem evolves into a cross-medium production task. These enums
# describe a task spanning publishing, graphic novels, film, audio and
# interactive work. ``ProductionItemStatus`` (above) is the shared lifecycle.


class ProductionTrack(str, Enum):
    """A discipline / pipeline lane a production task belongs to. Cross-medium:
    not every track is used by every division."""

    EDITORIAL = "editorial"
    ART = "art"
    LETTERING = "lettering"
    COLOR = "color"
    LAYOUT = "layout"
    PREPRESS = "prepress"
    PRINT = "print"
    SCRIPT = "script"
    STORYBOARD = "storyboard"
    ANIMATION = "animation"
    VFX = "vfx"
    PHOTOGRAPHY = "photography"
    EDITING = "editing"
    SOUND = "sound"
    MUSIC = "music"
    ENGINEERING = "engineering"
    DESIGN = "design"
    QA = "qa"
    MARKETING = "marketing"
    PRODUCTION = "production"
    OTHER = "other"


class ProductionTaskType(str, Enum):
    """The nature of a production task."""

    TASK = "task"
    REVIEW = "review"
    DELIVERABLE = "deliverable"
    APPROVAL = "approval"
    BUG = "bug"
    RESEARCH = "research"
    ADMIN = "admin"


class ProductionPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DependencyType(str, Enum):
    """How one task depends on another."""

    FINISH_TO_START = "finish_to_start"  # predecessor must finish before this starts
    START_TO_START = "start_to_start"
    RELATED = "related"


class MilestoneStatus(str, Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    REACHED = "reached"
    MISSED = "missed"
    CANCELLED = "cancelled"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"
    CANCELLED = "cancelled"


class ApprovalDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"


class ProductionActivityType(str, Enum):
    """An append-only event in a production task's history."""

    CREATED = "created"
    UPDATED = "updated"
    STATUS_CHANGED = "status_changed"
    ASSIGNED = "assigned"
    REASSIGNED = "reassigned"
    BLOCKED = "blocked"
    UNBLOCKED = "unblocked"
    DEPENDENCY_ADDED = "dependency_added"
    DEPENDENCY_REMOVED = "dependency_removed"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_DECIDED = "approval_decided"
    MILESTONE_LINKED = "milestone_linked"
    COMMENTED = "commented"
    COMPLETED = "completed"
    REOPENED = "reopened"
    TEMPLATE_APPLIED = "template_applied"


# --- Asset library ---------------------------------------------------------
# The central, work-centred asset domain. Distinct from ``Attachment`` (which
# stays a manuscript-scoped file record); assets are reusable, versioned and
# carry provenance and licensing.


class AssetType(str, Enum):
    """The kind of creative asset (cross-medium)."""

    IMAGE = "image"
    ILLUSTRATION = "illustration"
    CHARACTER_DESIGN = "character_design"
    ENVIRONMENT_DESIGN = "environment_design"
    COVER = "cover"
    PAGE_ART = "page_art"
    STORYBOARD = "storyboard"
    CONCEPT_ART = "concept_art"
    AUDIO = "audio"
    MUSIC = "music"
    SOUND_EFFECT = "sound_effect"
    VOICE = "voice"
    VIDEO = "video"
    ANIMATION = "animation"
    MODEL_3D = "model_3d"
    TEXTURE = "texture"
    FONT = "font"
    SCRIPT = "script"
    DOCUMENT = "document"
    OTHER = "other"


class AssetVisibility(str, Enum):
    """Who may see an asset. Even ``public_candidate`` assets are NEVER served
    directly through the public reader — public media uses the curated
    public projection. Visibility gates the *private* API only."""

    PRIVATE = "private"
    INTERNAL = "internal"
    RESTRICTED = "restricted"
    PUBLIC_CANDIDATE = "public_candidate"


class AssetApprovalStatus(str, Enum):
    """Human approval state of an asset version."""

    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class AssetLinkTargetType(str, Enum):
    """What an asset (or version) is attached to. Generic so it can reference
    entities that are not first-class tables (panels, scenes, shots)."""

    CHARACTER = "character"
    LOCATION = "location"
    KNOWLEDGE_ENTITY = "knowledge_entity"
    PAGE = "page"
    PANEL = "panel"
    SCENE = "scene"
    SHOT = "shot"
    PRODUCTION_TASK = "production_task"
    PUBLIC_READER_RECORD = "public_reader_record"
    WORK = "work"
    STORY_WORLD = "story_world"
    OTHER = "other"


class ProvenanceKind(str, Enum):
    HUMAN_CREATED = "human_created"
    AI_ASSISTED = "ai_assisted"
    AI_GENERATED = "ai_generated"
    MIXED = "mixed"


class CommercialUseReviewStatus(str, Enum):
    NOT_REVIEWED = "not_reviewed"
    UNDER_REVIEW = "under_review"
    CLEARED = "cleared"
    RESTRICTED = "restricted"
    BLOCKED = "blocked"


class LicenceType(str, Enum):
    PROPRIETARY = "proprietary"
    COMMISSIONED = "commissioned"
    WORK_FOR_HIRE = "work_for_hire"
    STOCK = "stock"
    CREATIVE_COMMONS = "creative_commons"
    PUBLIC_DOMAIN = "public_domain"
    ROYALTY_FREE = "royalty_free"
    RIGHTS_MANAGED = "rights_managed"
    AI_GENERATED = "ai_generated"
    OTHER = "other"


class LicenceReviewState(str, Enum):
    NOT_REVIEWED = "not_reviewed"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


# --- Graphic-novel production hierarchy -------------------------------------
# A detailed breakdown beneath GraphicNovelProduction (which stays the
# high-level summary): Volume → Chapter → Sequence → Page → Panel → element.


class GNStatus(str, Enum):
    """Workflow status of a node in the graphic-novel hierarchy."""

    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    COMPLETE = "complete"
    ON_HOLD = "on_hold"


class PageSide(str, Enum):
    LEFT = "left"  # verso
    RIGHT = "right"  # recto
    SINGLE = "single"


class CameraFraming(str, Enum):
    ESTABLISHING = "establishing"
    EXTREME_WIDE = "extreme_wide"
    WIDE = "wide"
    FULL = "full"
    MEDIUM = "medium"
    MEDIUM_CLOSE = "medium_close"
    CLOSE_UP = "close_up"
    EXTREME_CLOSE_UP = "extreme_close_up"
    INSERT = "insert"
    OTHER = "other"


class CameraAngle(str, Enum):
    EYE_LEVEL = "eye_level"
    HIGH = "high"
    LOW = "low"
    BIRDS_EYE = "birds_eye"
    WORMS_EYE = "worms_eye"
    DUTCH = "dutch"
    OVER_SHOULDER = "over_shoulder"
    POV = "pov"
    OTHER = "other"


class PanelElementType(str, Enum):
    CHARACTER = "character"
    PROP = "prop"
    LOCATION = "location"
    TEXT = "text"


class CurationStatus(str, Enum):
    """Where a page sits in the deliberate hand-off to the public reader. The
    public reader is NEVER written automatically — these are curation states
    only; an editor performs the actual publish separately."""

    NOT_READY = "not_ready"
    READY_FOR_CURATION = "ready_for_curation"
    IN_CURATION = "in_curation"
    HANDED_OFF = "handed_off"


# --- SUPERVOID Pictures (screen bounded context) ---------------------------
# An operational screen-production context entered via AdaptationDossier:
# ScreenProject → Episode/Reel → Sequence → Scene → Shot. Owns its own
# vocabulary so the context stays extractable; it reuses only genuinely shared
# camera/approval enums (CameraFraming, CameraAngle, AssetApprovalStatus).


class ScreenFormat(str, Enum):
    FILM = "film"
    SHORT = "short"
    SERIES = "series"
    ANIMATION = "animation"


class ScreenUnitType(str, Enum):
    """A top-level division of a screen project — an episode (series) or a reel
    / act / part (film, short, animation)."""

    EPISODE = "episode"
    REEL = "reel"
    ACT = "act"
    PART = "part"


class ScreenProjectStatus(str, Enum):
    DEVELOPMENT = "development"
    PRE_PRODUCTION = "pre_production"
    PRODUCTION = "production"
    POST_PRODUCTION = "post_production"
    DELIVERED = "delivered"
    ON_HOLD = "on_hold"
    CANCELLED = "cancelled"


class ScreenStatus(str, Enum):
    """Workflow status of a unit / sequence / scene / shot."""

    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    COMPLETE = "complete"
    ON_HOLD = "on_hold"


class SceneEnvironment(str, Enum):
    INT = "int"
    EXT = "ext"
    INT_EXT = "int_ext"


class SceneTimeOfDay(str, Enum):
    DAY = "day"
    NIGHT = "night"
    DAWN = "dawn"
    DUSK = "dusk"
    MORNING = "morning"
    EVENING = "evening"
    CONTINUOUS = "continuous"
    LATER = "later"
    UNSPECIFIED = "unspecified"


class ShotMovement(str, Enum):
    STATIC = "static"
    PAN = "pan"
    TILT = "tilt"
    DOLLY = "dolly"
    TRACK = "track"
    ZOOM = "zoom"
    CRANE = "crane"
    HANDHELD = "handheld"
    STEADICAM = "steadicam"
    AERIAL = "aerial"
    OTHER = "other"


# --- Supervised studio-agent framework -------------------------------------
# Evolves the manuscript AI layer into governed agents whose runs, findings and
# proposed actions are persisted. Read-only analysis runs immediately; mutations
# become proposals that a human must approve before execution.


class AgentMutability(str, Enum):
    """How much an agent is allowed to affect the system."""

    READ_ONLY = "read_only"  # analysis only; may never propose mutations
    PROPOSE_ONLY = "propose_only"  # may emit proposals, never auto-mutate


class AgentRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class FindingSeverity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AgentRiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ProposalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentToolKind(str, Enum):
    """The class of a registered tool, which governs how its output is handled.

    ``read_only`` tools may run during analysis; ``mutation`` and ``external``
    tools can only ever produce proposals that require explicit approval.
    """

    READ_ONLY = "read_only"
    MUTATION = "mutation"
    EXTERNAL = "external"


# --- Operational integration hub -------------------------------------------
# IntegrationPoint evolves from a descriptive registry into an operational but
# local-first hub. Code-registered adapters declare capabilities; every run is
# persisted, and external mutations pass through an approval boundary before
# any side effect can fire. Adapter keys / categories are stored as strings;
# only the run lifecycle and link kinds are DB enums.


class IntegrationAdapterKind(str, Enum):
    """The category of a code-registered integration adapter."""

    WEBHOOK = "webhook"  # generic outbound webhook (n8n, …)
    COMFYUI = "comfyui"  # local image/video generation backend
    GITHUB = "github"  # source-control project bridge
    FILE_EXCHANGE = "file_exchange"  # desktop-app export/import packages
    OTHER = "other"


class IntegrationRunStatus(str, Enum):
    """Lifecycle of a single integration operation.

    Read-only operations and dry-runs go straight to ``SUCCEEDED``. Operations
    that mutate internal state or touch an external system are created
    ``PENDING_APPROVAL`` and can only ever execute once ``APPROVED`` — this is
    the approval boundary external mutations must pass through.
    """

    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class IntegrationDirectionKind(str, Enum):
    """Which way an operation moves data relative to SUPERVOID Publishing."""

    INBOUND = "inbound"  # data flows into SUPERVOID
    OUTBOUND = "outbound"  # data flows out to the external system
    INTERNAL = "internal"  # local-only effect (e.g. write an export package)


class IntegrationHealthStatus(str, Enum):
    """Reported health of an adapter for a configured integration point."""

    HEALTHY = "healthy"  # configured and (where checked) reachable
    DEGRADED = "degraded"  # configured but partially usable
    UNREACHABLE = "unreachable"  # configured but not responding
    NOT_CONFIGURED = "not_configured"  # missing required configuration
    DISABLED = "disabled"  # the integration point is switched off
    UNKNOWN = "unknown"  # liveness not checked (local-first default)


class IntegrationLinkKind(str, Enum):
    """The kind of external object linked to an internal production task."""

    COMMIT = "commit"
    ISSUE = "issue"
    PULL_REQUEST = "pull_request"
    BRANCH = "branch"
    RELEASE = "release"
    OTHER = "other"


# --- Business layer: rights depth ------------------------------------------
# Deepen the Rights/Contract layer for an independent studio: term windows,
# exclusivity, sublicensing, options, chain of title, evidence and history.


class RightsExclusivity(str, Enum):
    EXCLUSIVE = "exclusive"
    SOLE = "sole"  # licensor may also exploit, but no other licensees
    NON_EXCLUSIVE = "non_exclusive"
    UNSPECIFIED = "unspecified"


class RightScope(str, Enum):
    """A licensable right, used by windows / options / status history."""

    PRINT = "print"
    EBOOK = "ebook"
    AUDIOBOOK = "audiobook"
    FILM = "film"
    TELEVISION = "television"
    STAGE = "stage"
    TRANSLATION = "translation"
    SERIAL = "serial"
    ADAPTATION = "adaptation"
    MERCHANDISING = "merchandising"
    GAMING = "gaming"
    ALL = "all"
    OTHER = "other"


class RightsWindowStatus(str, Enum):
    PLANNED = "planned"
    ACTIVE = "active"
    EXPIRED = "expired"
    TERMINATED = "terminated"
    REVERTED = "reverted"


class OptionPeriodStatus(str, Enum):
    OPEN = "open"
    EXERCISED = "exercised"
    EXPIRED = "expired"
    DECLINED = "declined"


class ChainOfTitleType(str, Enum):
    CREATION = "creation"
    ASSIGNMENT = "assignment"
    LICENSE = "license"
    WORK_FOR_HIRE = "work_for_hire"
    INHERITANCE = "inheritance"
    REVERSION = "reversion"
    OTHER = "other"


class RightsEvidenceKind(str, Enum):
    CONTRACT = "contract"
    AMENDMENT = "amendment"
    ASSIGNMENT = "assignment"
    REGISTRATION = "registration"
    CORRESPONDENCE = "correspondence"
    RELEASE = "release"
    LICENSE = "license"
    OTHER = "other"


# --- Business layer: relationship memory (CRM) -----------------------------
# A private studio CRM. Manual logging only — never scrapes or sends
# unsolicited communication automatically.


class OrganizationKind(str, Enum):
    PUBLISHER = "publisher"
    DISTRIBUTOR = "distributor"
    PRINTER = "printer"
    RETAILER = "retailer"
    FESTIVAL = "festival"
    AGENCY = "agency"
    MEDIA = "media"
    STUDIO = "studio"
    INSTITUTION = "institution"
    OTHER = "other"


class ContactRoleKind(str, Enum):
    PUBLISHER = "publisher"
    DISTRIBUTOR = "distributor"
    PRINTER = "printer"
    JOURNALIST = "journalist"
    REVIEWER = "reviewer"
    FESTIVAL = "festival"
    TRANSLATOR = "translator"
    ARTIST = "artist"
    AGENT = "agent"
    COLLABORATOR = "collaborator"
    EDITOR = "editor"
    RETAILER = "retailer"
    OTHER = "other"


class InteractionKind(str, Enum):
    EMAIL = "email"
    CALL = "call"
    MEETING = "meeting"
    EVENT = "event"
    SUBMISSION = "submission"
    SOCIAL = "social"
    NOTE = "note"
    OTHER = "other"


class InteractionDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    INTERNAL = "internal"


class ConsentStatus(str, Enum):
    """Consent to be contacted — manual, recorded, never assumed."""

    UNKNOWN = "unknown"
    GRANTED = "granted"
    DECLINED = "declined"
    WITHDRAWN = "withdrawn"


class OpportunityKind(str, Enum):
    RIGHTS_SALE = "rights_sale"
    CO_EDITION = "co_edition"
    TRANSLATION = "translation"
    REVIEW = "review"
    FESTIVAL = "festival"
    DISTRIBUTION = "distribution"
    COLLABORATION = "collaboration"
    SPONSORSHIP = "sponsorship"
    OTHER = "other"


class OpportunityStatus(str, Enum):
    LEAD = "lead"
    QUALIFIED = "qualified"
    ACTIVE = "active"
    NEGOTIATION = "negotiation"
    WON = "won"
    LOST = "lost"
    DORMANT = "dormant"


# --- Business layer: editions & distribution -------------------------------
# A proper Edition model (connected to ProductionRecord) plus validated
# distribution-package generators.


class EditionFormat(str, Enum):
    HARDCOVER = "hardcover"
    TRADE_PAPERBACK = "trade_paperback"
    MASS_MARKET = "mass_market"
    POD_PAPERBACK = "pod_paperback"
    EBOOK = "ebook"
    AUDIOBOOK = "audiobook"
    WEB_COMIC = "web_comic"
    PDF = "pdf"
    BOX_SET = "box_set"
    OTHER = "other"


class EditionIdentifierType(str, Enum):
    ISBN_13 = "isbn_13"
    ISBN_10 = "isbn_10"
    ASIN = "asin"
    DOI = "doi"
    UPC = "upc"
    INTERNAL = "internal"
    NONE = "none"


class DistributionStatus(str, Enum):
    PLANNED = "planned"
    IN_PREP = "in_prep"
    READY = "ready"
    SUBMITTED = "submitted"
    LIVE = "live"
    ON_HOLD = "on_hold"
    OUT_OF_PRINT = "out_of_print"
    WITHDRAWN = "withdrawn"


class DistributionChannel(str, Enum):
    """A target for a generated, validated distribution package."""

    ONIX = "onix"
    KDP = "kdp"
    INGRAM = "ingram"
    GLOBALCOMIX = "globalcomix"
    PRESS_KIT = "press_kit"
    ARC = "arc"


class PackageStatus(str, Enum):
    GENERATED = "generated"  # built, not yet validated
    VALIDATED = "validated"  # built and passed validation
    INVALID = "invalid"  # built but failed validation
    FAILED = "failed"  # generation itself errored


class ChecklistStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    NA = "na"


# --- Private curation of the public reader ---------------------------------
# A private admin CMS curates the public projection and performs a controlled
# hand-off from private GraphicNovelPage / AssetVersion records. Publication is
# gated behind validation + approval; history is preserved; the public reader is
# never written automatically and never references a private file.


class PublicationAction(str, Enum):
    """An append-only event in a published work's history."""

    CREATED = "created"
    UPDATED = "updated"
    SCHEDULED = "scheduled"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"
    UNPUBLISHED = "unpublished"
    ARCHIVED = "archived"
    PAGE_HANDED_OFF = "page_handed_off"


class PublicationApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PanelTransition(str, Enum):
    """How the cinematic reader moves between panels."""

    CUT = "cut"
    FADE = "fade"
    DISSOLVE = "dissolve"
    SLIDE = "slide"
    ZOOM = "zoom"
