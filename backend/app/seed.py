"""Database seed entrypoint.

Run with::

    python -m app.seed

Idempotent: if the users table is already populated the seed is a no-op.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlmodel import Session, select

from app.auth.security import hash_password
from app.db import engine, init_db
from app.models import (
    Author,
    CalendarEventStatus,
    CalendarEventType,
    Contract,
    ContractStatus,
    EditorialNote,
    EditorialNoteKind,
    EntityKind,
    GraphicNovelProduction,
    IntegrationPoint,
    IntegrationPointStatus,
    IntegrationPointType,
    KnowledgeEntity,
    KnowledgeRelationship,
    Manuscript,
    ManuscriptEntityLink,
    ManuscriptLinkRole,
    ProductionItem,
    ProductionItemStatus,
    ProductionRecord,
    ProductionStage,
    PublishingCalendarEvent,
    RelationshipKind,
    Review,
    ReviewVerdict,
    Rights,
    RightStatus,
    StreamStatus,
    User,
    UserRole,
    Work,
    WorkflowEvent,
    WorkflowStatus,
    WorkStatus,
    WorkType,
)
from app.models import (  # public reader projection
    HotspotType,
    MediaAssetType,
    PanelTransition,
    PublicationAction,
    PublicationApproval,
    PublicationApprovalStatus,
    PublicationEvent,
    PublicHotspot,
    PublicMediaAsset,
    PublishedChapter,
    PublishedPage,
    PublishedPanel,
    PublishedStatus,
    PublishedVolume,
    PublishedWork,
)
from app.models import (  # IP / transmedia layer
    AdaptationDossier,
    AdaptationStatus,
    CanonState,
    Medium,
    RightsClearanceState,
    StorySeries,
    StorySeriesStatus,
    StoryWorld,
    StoryWorldStatus,
    StudioDivision,
)
from app.models import (  # collaboration / project-scoped access
    MembershipAuditAction,
    MembershipStatus,
    ProjectMembership,
    ProjectRole,
)
from app.models import ApprovalRequest  # production task system
from app.models import (  # graphic-novel hierarchy
    CameraAngle,
    CameraFraming,
    GNStatus,
    GraphicNovelChapter,
    GraphicNovelPage,
    GraphicNovelPageEntityLink,
    GraphicNovelPanel,
    GraphicNovelPanelElement,
    GraphicNovelSequence,
    GraphicNovelVolume,
    PageSide,
    PanelElementType,
)
from app.models import (  # asset library
    Asset,
    AssetApprovalStatus,
    AssetLink,
    AssetLinkTargetType,
    AssetType,
    AssetVersion,
    AssetVisibility,
    CommercialUseReviewStatus,
    LicenceRecord,
    LicenceReviewState,
    LicenceType,
    ProvenanceKind,
    ProvenanceRecord,
)
from app.models import (  # SUPERVOID Pictures
    Scene,
    SceneCharacterLink,
    SceneEnvironment,
    SceneTimeOfDay,
    ScreenFormat,
    ScreenSequence,
    ScreenShotPanelLink,
    Shot,
    ShotMovement,
)
from app.models import PromptTemplate, PromptTemplateVersion  # agent framework
from app.models import (  # business layer (rights depth / CRM / editions)
    ChainOfTitleEntry,
    ChainOfTitleType,
    ConsentStatus,
    Contact,
    ContactRole,
    ContactRoleKind,
    ContactTag,
    ContactTagLink,
    DistributionChannel,
    DistributionStatus,
    Edition,
    EditionFormat,
    EditionIdentifierType,
    Interaction,
    InteractionDirection,
    InteractionKind,
    Opportunity,
    OpportunityKind,
    OpportunityStatus,
    OptionPeriodStatus,
    Organization,
    OrganizationKind,
    RightScope,
    RightsEvidence,
    RightsEvidenceKind,
    RightsExclusivity,
    RightsOption,
    RightsStatusHistory,
    RightsWindow,
    RightsWindowStatus,
)
from app.services import agents as agent_svc
from app.services import distribution as distribution_svc
from app.services import integrations as integration_hub
from app.services.knowledge import slugify as _slugify_tag
from app.services import graphic_novel as gn_service
from app.services import policy
from app.services import screen as screen_service
from app.services import production as production_service
from app.services import production_templates
from app.services.knowledge import slugify
from app.services.public_reader_service import publish_work_to_public_reader
from app.models.base import utcnow

# A single demo password keyed for every seeded user; documented in the README.
DEMO_PASSWORD = "supervoid"


def _user(email: str, full_name: str, role: UserRole) -> User:
    return User(
        email=email,
        full_name=full_name,
        role=role,
        hashed_password=hash_password(DEMO_PASSWORD),
    )


def _seed_users(session: Session) -> dict[str, User]:
    users = {
        # Editorial leadership and editors.
        "helena": _user("helena.pryce@supervoid.local", "Helena Pryce", UserRole.ADMIN),
        "jonas": _user("jonas.marten@supervoid.local", "Jonas Mårten", UserRole.EDITOR),
        "cecilia": _user("cecilia.dore@supervoid.local", "Cecilia Doré", UserRole.EDITOR),
        "tomas": _user("tomas.aribau@supervoid.local", "Tomás Aribau", UserRole.EDITOR),
        "ruth": _user("ruth.engstrom@supervoid.local", "Ruth Engström", UserRole.EDITOR),
        # External / structural reviewer.
        "bartholomew": _user(
            "bartholomew.krause@supervoid.local",
            "Bartholomew Krause",
            UserRole.REVIEWER,
        ),
        # Production.
        "kazu": _user(
            "kazu.fujita@supervoid.local", "Kazu Fujita", UserRole.PRODUCTION_MANAGER
        ),
        "ines": _user(
            "ines.harlan@supervoid.local", "Inés Harlan", UserRole.PRODUCTION_MANAGER
        ),
        # Marketing and archive.
        "mireille": _user(
            "mireille.vance@supervoid.local", "Mireille Vance", UserRole.MARKETING
        ),
        "olesya": _user(
            "olesya.kestral@supervoid.local", "Olesya Kestral", UserRole.ARCHIVE_READER
        ),
    }
    session.add_all(users.values())
    session.commit()
    for u in users.values():
        session.refresh(u)
    return users


def _seed_authors(session: Session) -> dict[str, Author]:
    authors = {
        "aldoria": Author(
            full_name="Iris Aldoria",
            email="iris.aldoria@example.org",
            country="Portugal",
            biography="Essayist and cartographer of inland seas; previous fellow at the Lisbon Atheneum.",
        ),
        "veldt": Author(
            full_name="Marcus Veldt",
            email="marcus.veldt@example.org",
            country="Netherlands",
            biography="Novelist of correspondences and provincial life.",
        ),
        "carrick": Author(
            full_name="Saoirse Carrick",
            email="saoirse.carrick@example.org",
            country="Ireland",
            biography="Short-form writer; debut novella under consideration.",
        ),
        "bellecour": Author(
            full_name="Diane Bellecour",
            email="d.bellecour@example.org",
            country="France",
            biography="Naturalist; lecturer at the Muséum, writing in the Buffon tradition.",
        ),
        "tanigawa": Author(
            full_name="Hideo Tanigawa",
            email="h.tanigawa@example.org",
            country="Japan",
            biography="Debut novelist; trained as a typographer in Kyoto.",
        ),
    }
    session.add_all(authors.values())
    session.commit()
    for a in authors.values():
        session.refresh(a)
    return authors


def _seed_manuscripts(
    session: Session, authors: dict[str, Author]
) -> dict[str, Manuscript]:
    manuscripts = {
        "salt_atlases": Manuscript(
            title="The Salt Atlases",
            subtitle="A cartography of inland seas",
            synopsis=(
                "Twelve essays on the inland seas of Europe and the librarians "
                "who mapped them."
            ),
            work_type=WorkType.BOOK,
            genre="Essays",
            word_count=68200,
            status=WorkflowStatus.PUBLISHED,
            author_id=authors["aldoria"].id,
        ),
        "letters_dim": Manuscript(
            title="Letters to a Dim Province",
            synopsis=(
                "An epistolary novel set in a forgotten provincial capital at "
                "the turn of a century."
            ),
            work_type=WorkType.BOOK,
            genre="Fiction",
            word_count=92400,
            status=WorkflowStatus.COPY_EDITING,
            author_id=authors["veldt"].id,
        ),
        "silent_workshop": Manuscript(
            title="The Silent Workshop",
            synopsis=(
                "A graphic novel concerning a printer who corresponds for forty "
                "years with a binder he never meets."
            ),
            work_type=WorkType.GRAPHIC_NOVEL,
            genre="Graphic novel",
            word_count=41800,
            status=WorkflowStatus.UNDER_REVIEW,
            author_id=authors["carrick"].id,
        ),
        "algebra_birds": Manuscript(
            title="Algebra of Birds",
            synopsis=(
                "A natural philosophy of flock formation, written in the "
                "tradition of Buffon and richly plated."
            ),
            work_type=WorkType.ART_BOOK,
            genre="Natural history",
            word_count=54100,
            status=WorkflowStatus.DEVELOPMENT_EDITING,
            author_id=authors["bellecour"].id,
        ),
        "quintus": Manuscript(
            title="Quintus, the Foundry",
            synopsis=(
                "A debut novel concerning a typefounder in late "
                "nineteenth-century Kyoto."
            ),
            work_type=WorkType.BOOK,
            genre="Fiction",
            word_count=78900,
            status=WorkflowStatus.SUBMITTED,
            author_id=authors["tanigawa"].id,
        ),
    }
    session.add_all(manuscripts.values())
    session.commit()
    for m in manuscripts.values():
        session.refresh(m)
    return manuscripts


# Maturity of the manuscript workflow mapped onto the Work lifecycle.
_WORK_STATUS_BY_MS_KEY = {
    "salt_atlases": WorkStatus.PUBLISHED,
    "letters_dim": WorkStatus.IN_PRODUCTION,
    "silent_workshop": WorkStatus.IN_DEVELOPMENT,
    "algebra_birds": WorkStatus.IN_DEVELOPMENT,
    "quintus": WorkStatus.CONCEPT,
}


def _seed_works(
    session: Session,
    authors: dict[str, Author],
    manuscripts: dict[str, Manuscript],
) -> dict[str, Work]:
    """Promote each demo manuscript to a catalogue Work and link them, then
    add one future-adaptation-candidate Work for the SUPERVOID Movies seam."""

    works: dict[str, Work] = {}
    for key, ms in manuscripts.items():
        works[key] = Work(
            title=ms.title,
            subtitle=ms.subtitle,
            work_type=ms.work_type,
            genre=ms.genre,
            status=_WORK_STATUS_BY_MS_KEY.get(key, WorkStatus.CONCEPT),
            synopsis=ms.synopsis,
            language=ms.language,
            word_count=ms.word_count,
            author_id=ms.author_id,
        )

    # A book and a graphic novel get a little extra catalogue detail.
    works["salt_atlases"].internal_pitch = (
        "Lead non-fiction title; a literary atlas with strong gift-market appeal."
    )
    works["salt_atlases"].target_audience = "Literary non-fiction; map and travel readers."
    works["salt_atlases"].page_count = 288
    works["silent_workshop"].internal_pitch = (
        "Flagship graphic novel; quiet, prestige, awards-track."
    )
    works["silent_workshop"].target_audience = "Adult literary comics readers."
    works["silent_workshop"].page_count = 176

    # Future adaptation candidate — pairs with the SUPERVOID Movies seam.
    works["workshop_screen"] = Work(
        title="The Silent Workshop — Screen Treatment",
        subtitle="Adaptation candidate",
        work_type=WorkType.ADAPTATION_CANDIDATE,
        genre="Drama",
        status=WorkStatus.CONCEPT,
        synopsis=(
            "Exploratory screen treatment of The Silent Workshop, flagged for "
            "the SUPERVOID Movies division to evaluate."
        ),
        internal_pitch="Prestige limited-series potential; rights currently held in-house.",
        target_audience="Screen development / co-production partners.",
        language="en",
        author_id=authors["carrick"].id,
    )

    session.add_all(works.values())
    session.commit()
    for w in works.values():
        session.refresh(w)

    # Link each text manuscript back to its Work.
    for key, ms in manuscripts.items():
        ms.work_id = works[key].id
        session.add(ms)
    session.commit()

    return works


def _event(
    manuscript: Manuscript,
    to_status: WorkflowStatus,
    *,
    from_status: WorkflowStatus | None = None,
    actor: User | None = None,
    note: str | None = None,
) -> WorkflowEvent:
    return WorkflowEvent(
        manuscript_id=manuscript.id,
        actor_id=actor.id if actor else None,
        from_status=from_status,
        to_status=to_status,
        note=note,
    )


def _seed_workflow_events(
    session: Session,
    manuscripts: dict[str, Manuscript],
    users: dict[str, User],
) -> None:
    events: list[WorkflowEvent] = []

    # The Salt Atlases — the full editorial journey through to publication.
    salt = manuscripts["salt_atlases"]
    salt_journey: list[tuple[WorkflowStatus | None, WorkflowStatus, User | None]] = [
        (None, WorkflowStatus.SUBMITTED, None),
        (WorkflowStatus.SUBMITTED, WorkflowStatus.UNDER_REVIEW, users["jonas"]),
        (WorkflowStatus.UNDER_REVIEW, WorkflowStatus.ACCEPTED, users["helena"]),
        (WorkflowStatus.ACCEPTED, WorkflowStatus.DEVELOPMENT_EDITING, users["cecilia"]),
        (WorkflowStatus.DEVELOPMENT_EDITING, WorkflowStatus.COPY_EDITING, users["tomas"]),
        (WorkflowStatus.COPY_EDITING, WorkflowStatus.PROOFREADING, users["ruth"]),
        (WorkflowStatus.PROOFREADING, WorkflowStatus.LAYOUT, users["kazu"]),
        (WorkflowStatus.LAYOUT, WorkflowStatus.COVER_DESIGN, users["kazu"]),
        (WorkflowStatus.COVER_DESIGN, WorkflowStatus.PREPRESS, users["ines"]),
        (WorkflowStatus.PREPRESS, WorkflowStatus.PUBLISHED, users["ines"]),
    ]
    for prev, nxt, actor in salt_journey:
        events.append(_event(salt, nxt, from_status=prev, actor=actor))

    # Letters to a Dim Province — through to copy editing.
    letters = manuscripts["letters_dim"]
    for prev, nxt, actor in [
        (None, WorkflowStatus.SUBMITTED, None),
        (WorkflowStatus.SUBMITTED, WorkflowStatus.UNDER_REVIEW, users["jonas"]),
        (WorkflowStatus.UNDER_REVIEW, WorkflowStatus.ACCEPTED, users["helena"]),
        (WorkflowStatus.ACCEPTED, WorkflowStatus.DEVELOPMENT_EDITING, users["cecilia"]),
        (WorkflowStatus.DEVELOPMENT_EDITING, WorkflowStatus.COPY_EDITING, users["tomas"]),
    ]:
        events.append(_event(letters, nxt, from_status=prev, actor=actor))

    # The Silent Workshop — currently under review.
    workshop = manuscripts["silent_workshop"]
    events.append(_event(workshop, WorkflowStatus.SUBMITTED))
    events.append(
        _event(
            workshop,
            WorkflowStatus.UNDER_REVIEW,
            from_status=WorkflowStatus.SUBMITTED,
            actor=users["cecilia"],
        )
    )

    # Algebra of Birds — in development editing.
    birds = manuscripts["algebra_birds"]
    for prev, nxt, actor in [
        (None, WorkflowStatus.SUBMITTED, None),
        (WorkflowStatus.SUBMITTED, WorkflowStatus.UNDER_REVIEW, users["jonas"]),
        (WorkflowStatus.UNDER_REVIEW, WorkflowStatus.ACCEPTED, users["helena"]),
        (WorkflowStatus.ACCEPTED, WorkflowStatus.DEVELOPMENT_EDITING, users["cecilia"]),
    ]:
        events.append(_event(birds, nxt, from_status=prev, actor=actor))

    # Quintus — newly arrived.
    events.append(_event(manuscripts["quintus"], WorkflowStatus.SUBMITTED))

    session.add_all(events)
    session.commit()


def _seed_reviews(
    session: Session,
    manuscripts: dict[str, Manuscript],
    works: dict[str, Work],
    users: dict[str, User],
) -> None:
    reviews = [
        Review(
            manuscript_id=manuscripts["silent_workshop"].id,
            work_id=works["silent_workshop"].id,
            reviewer_id=users["jonas"].id,
            verdict=ReviewVerdict.REVISE,
            summary=(
                "A spare, beautifully restrained novella. The middle third "
                "drifts; the closing letters should arrive earlier."
            ),
            written_report=(
                "Structurally the central correspondence sags between pages "
                "60 and 110; the emotional payload of the final letters would "
                "land harder brought forward. Art direction is exceptional."
            ),
            rating=4,
            literary_quality_score=4,
            visual_potential_score=5,
            market_potential_score=3,
            originality_score=4,
            editorial_effort_score=3,
        ),
        Review(
            manuscript_id=manuscripts["silent_workshop"].id,
            work_id=works["silent_workshop"].id,
            reviewer_id=users["cecilia"].id,
            verdict=ReviewVerdict.ACCEPT,
            summary="An assured debut, ready with minor structural notes.",
            rating=4,
            literary_quality_score=4,
            visual_potential_score=5,
            market_potential_score=4,
            originality_score=4,
            editorial_effort_score=2,
        ),
        Review(
            manuscript_id=manuscripts["algebra_birds"].id,
            work_id=works["algebra_birds"].id,
            reviewer_id=users["jonas"].id,
            verdict=ReviewVerdict.ACCEPT,
            summary=(
                "Original synthesis. The Buffon framing is earned. Recommend "
                "acceptance with light development work."
            ),
            rating=5,
            literary_quality_score=5,
            visual_potential_score=4,
            market_potential_score=3,
            originality_score=5,
            editorial_effort_score=3,
        ),
        Review(
            manuscript_id=manuscripts["quintus"].id,
            work_id=works["quintus"].id,
            reviewer_id=users["bartholomew"].id,
            verdict=ReviewVerdict.HOLD,
            summary="Promising voice; hold pending a second structural read.",
            rating=3,
            literary_quality_score=4,
            market_potential_score=2,
            originality_score=4,
            editorial_effort_score=4,
        ),
        Review(
            manuscript_id=manuscripts["letters_dim"].id,
            work_id=works["letters_dim"].id,
            reviewer_id=users["helena"].id,
            verdict=ReviewVerdict.ACCEPT,
            summary="Marquee voice. Proceeding to acquisition.",
            rating=5,
            literary_quality_score=5,
            market_potential_score=4,
            originality_score=4,
            editorial_effort_score=2,
        ),
    ]
    session.add_all(reviews)
    session.commit()


def _seed_contracts(
    session: Session,
    manuscripts: dict[str, Manuscript],
    works: dict[str, Work],
    authors: dict[str, Author],
) -> None:
    today = date.today()
    contracts = [
        Contract(
            manuscript_id=manuscripts["salt_atlases"].id,
            work_id=works["salt_atlases"].id,
            author_id=authors["aldoria"].id,
            status=ContractStatus.SIGNED,
            advance_amount=Decimal("4500.00"),
            royalty_rate=0.12,
            currency="EUR",
            rights_territory="world",
            signed_at=utcnow() - timedelta(days=300),
            expiration_date=today + timedelta(days=365 * 6),
            terms="Standard trade contract, first edition only.",
        ),
        Contract(
            manuscript_id=manuscripts["letters_dim"].id,
            work_id=works["letters_dim"].id,
            author_id=authors["veldt"].id,
            status=ContractStatus.SIGNED,
            advance_amount=Decimal("7500.00"),
            royalty_rate=0.15,
            currency="EUR",
            rights_territory="europe",
            signed_at=utcnow() - timedelta(days=180),
            expiration_date=today + timedelta(days=365 * 7),
        ),
        Contract(
            manuscript_id=manuscripts["algebra_birds"].id,
            work_id=works["algebra_birds"].id,
            author_id=authors["bellecour"].id,
            status=ContractStatus.DRAFT,
            advance_amount=Decimal("3000.00"),
            royalty_rate=0.10,
            currency="EUR",
            rights_territory="world",
        ),
    ]
    session.add_all(contracts)
    session.commit()


def _seed_production_items(
    session: Session,
    manuscripts: dict[str, Manuscript],
    works: dict[str, Work],
    users: dict[str, User],
) -> None:
    today = date.today()
    items = [
        ProductionItem(
            manuscript_id=manuscripts["salt_atlases"].id,
            work_id=works["salt_atlases"].id,
            assignee_id=users["kazu"].id,
            stage=ProductionStage.COVER_DESIGN,
            status=ProductionItemStatus.DONE,
            due_date=today - timedelta(days=80),
            notes="Linen wrap, foil debossed title; signed off.",
        ),
        ProductionItem(
            manuscript_id=manuscripts["salt_atlases"].id,
            work_id=works["salt_atlases"].id,
            assignee_id=users["ines"].id,
            stage=ProductionStage.PRINTING,
            status=ProductionItemStatus.DONE,
            due_date=today - timedelta(days=35),
        ),
        ProductionItem(
            manuscript_id=manuscripts["letters_dim"].id,
            work_id=works["letters_dim"].id,
            assignee_id=users["kazu"].id,
            stage=ProductionStage.LAYOUT,
            status=ProductionItemStatus.IN_PROGRESS,
            due_date=today + timedelta(days=21),
            notes="Twelve-point Garamond, generous margins; first proofs next week.",
        ),
        ProductionItem(
            manuscript_id=manuscripts["letters_dim"].id,
            work_id=works["letters_dim"].id,
            assignee_id=users["kazu"].id,
            stage=ProductionStage.COVER_DESIGN,
            status=ProductionItemStatus.PENDING,
            due_date=today + timedelta(days=45),
        ),
    ]
    session.add_all(items)
    session.commit()


def _seed_editorial_notes(
    session: Session,
    manuscripts: dict[str, Manuscript],
    works: dict[str, Work],
    authors: dict[str, Author],
    users: dict[str, User],
) -> None:
    notes = [
        EditorialNote(
            manuscript_id=manuscripts["silent_workshop"].id,
            work_id=works["silent_workshop"].id,
            author_id=authors["carrick"].id,
            author_user_id=users["cecilia"].id,
            kind=EditorialNoteKind.STRUCTURAL,
            body=(
                "Consider compressing the central correspondence into a single "
                "dated sequence; the present arrangement frays the through-line."
            ),
            pinned=True,
        ),
        EditorialNote(
            manuscript_id=manuscripts["algebra_birds"].id,
            work_id=works["algebra_birds"].id,
            author_user_id=users["jonas"].id,
            kind=EditorialNoteKind.GENERAL,
            body=(
                "The mathematical appendices want a separate fold-out plate; "
                "coordinate with design before copy editing begins."
            ),
        ),
        EditorialNote(
            manuscript_id=manuscripts["letters_dim"].id,
            work_id=works["letters_dim"].id,
            author_user_id=users["tomas"].id,
            kind=EditorialNoteKind.LINE,
            body=(
                "Pass two complete; queries deferred to author. Awaiting "
                "clarification on chapter eleven."
            ),
        ),
    ]
    session.add_all(notes)
    session.commit()


def _seed_production_records(
    session: Session, manuscripts: dict[str, Manuscript]
) -> None:
    today = date.today()
    records = [
        # The Salt Atlases — already out in the world.
        ProductionRecord(
            manuscript_id=manuscripts["salt_atlases"].id,
            isbn="978-3-16-148410-0",
            release_date=today - timedelta(days=30),
            print_status=StreamStatus.COMPLETE,
            ebook_status=StreamStatus.COMPLETE,
            audiobook_status=StreamStatus.NOT_PLANNED,
            cover_status=StreamStatus.COMPLETE,
            layout_status=StreamStatus.COMPLETE,
            prepress_status=StreamStatus.COMPLETE,
            notes="Boxed up · stock in the warehouse · awaiting reviews.",
        ),
        # Letters to a Dim Province — actively in production.
        ProductionRecord(
            manuscript_id=manuscripts["letters_dim"].id,
            isbn="978-3-16-148411-7",
            release_date=today + timedelta(days=120),
            print_status=StreamStatus.PENDING,
            ebook_status=StreamStatus.PENDING,
            audiobook_status=StreamStatus.NOT_PLANNED,
            cover_status=StreamStatus.IN_PROGRESS,
            layout_status=StreamStatus.IN_PROGRESS,
            prepress_status=StreamStatus.NOT_PLANNED,
            notes="Hardcover only for first edition; ebook to follow at +30 days.",
        ),
        # Algebra of Birds — schedule penciled, work not yet begun.
        ProductionRecord(
            manuscript_id=manuscripts["algebra_birds"].id,
            isbn=None,
            release_date=today + timedelta(days=300),
            print_status=StreamStatus.PENDING,
            ebook_status=StreamStatus.PENDING,
            audiobook_status=StreamStatus.PENDING,
            cover_status=StreamStatus.NOT_PLANNED,
            layout_status=StreamStatus.NOT_PLANNED,
            prepress_status=StreamStatus.NOT_PLANNED,
            notes="Discussions underway for plate insert; budget pending.",
        ),
    ]
    session.add_all(records)
    session.commit()


def _seed_rights(session: Session, works: dict[str, Work]) -> None:
    today = date.today()
    rights = [
        # The Salt Atlases (book) — primary world English edition held in-house.
        Rights(
            work_id=works["salt_atlases"].id,
            territory="World",
            language="English",
            print_rights=RightStatus.LICENSED,
            ebook_rights=RightStatus.LICENSED,
            audiobook_rights=RightStatus.AVAILABLE,
            film_rights=RightStatus.AVAILABLE,
            adaptation_rights=RightStatus.AVAILABLE,
            merchandising_rights=RightStatus.NOT_APPLICABLE,
            holder="SUPERVOID Publishing",
            notes="Primary edition rights held in-house; translation open.",
        ),
        # A separate translation window, currently under option.
        Rights(
            work_id=works["salt_atlases"].id,
            territory="World",
            language="French",
            print_rights=RightStatus.OPTIONED,
            ebook_rights=RightStatus.OPTIONED,
            audiobook_rights=RightStatus.AVAILABLE,
            film_rights=RightStatus.NOT_APPLICABLE,
            adaptation_rights=RightStatus.NOT_APPLICABLE,
            merchandising_rights=RightStatus.NOT_APPLICABLE,
            expiration_date=today + timedelta(days=180),
            notes="French-language option with Éditions du Phare.",
        ),
        # The Silent Workshop (graphic novel) — screen rights reserved for SV Movies.
        Rights(
            work_id=works["silent_workshop"].id,
            territory="World",
            language="all",
            print_rights=RightStatus.RESERVED,
            ebook_rights=RightStatus.RESERVED,
            audiobook_rights=RightStatus.NOT_APPLICABLE,
            film_rights=RightStatus.RESERVED,
            adaptation_rights=RightStatus.RESERVED,
            merchandising_rights=RightStatus.AVAILABLE,
            holder="SUPERVOID Publishing",
            notes="Film/adaptation reserved pending SUPERVOID Movies evaluation.",
        ),
    ]
    session.add_all(rights)
    session.commit()


def _seed_graphic_novel_production(
    session: Session, works: dict[str, Work]
) -> None:
    production = GraphicNovelProduction(
        work_id=works["silent_workshop"].id,
        volume_number=1,
        script_status=StreamStatus.COMPLETE,
        storyboard_status=StreamStatus.IN_PROGRESS,
        character_design_status=StreamStatus.COMPLETE,
        environment_design_status=StreamStatus.IN_PROGRESS,
        page_layout_status=StreamStatus.PENDING,
        lettering_status=StreamStatus.NOT_PLANNED,
        coloring_status=StreamStatus.NOT_PLANNED,
        final_files_status=StreamStatus.NOT_PLANNED,
        notes="Single-volume graphic novel; interiors in greyscale wash.",
    )
    session.add(production)
    session.commit()


def _seed_calendar_events(session: Session, works: dict[str, Work]) -> None:
    today = date.today()
    events = [
        PublishingCalendarEvent(
            work_id=works["salt_atlases"].id,
            title="The Salt Atlases — on sale",
            event_type=CalendarEventType.RELEASE,
            date=today - timedelta(days=30),
            description="Trade hardcover release.",
            status=CalendarEventStatus.COMPLETED,
        ),
        PublishingCalendarEvent(
            work_id=works["letters_dim"].id,
            title="Letters to a Dim Province — cover reveal",
            event_type=CalendarEventType.COVER_REVEAL,
            date=today + timedelta(days=20),
            description="Reveal across trade and social channels.",
            status=CalendarEventStatus.CONFIRMED,
        ),
        PublishingCalendarEvent(
            work_id=works["letters_dim"].id,
            title="Letters to a Dim Province — on sale",
            event_type=CalendarEventType.RELEASE,
            date=today + timedelta(days=120),
            description="Hardcover first edition.",
            status=CalendarEventStatus.PLANNED,
        ),
        PublishingCalendarEvent(
            work_id=works["silent_workshop"].id,
            title="The Silent Workshop — preorder opens",
            event_type=CalendarEventType.PREORDER,
            date=today + timedelta(days=60),
            status=CalendarEventStatus.PLANNED,
        ),
        PublishingCalendarEvent(
            work_id=None,
            title="Autumn catalogue deadline",
            event_type=CalendarEventType.OTHER,
            date=today + timedelta(days=45),
            description="House-wide: all autumn metadata locked.",
            status=CalendarEventStatus.PLANNED,
        ),
    ]
    session.add_all(events)
    session.commit()


def _seed_integration_points(session: Session) -> dict[str, IntegrationPoint]:
    """Seed the integration registry, now binding operational, local-first
    adapters. Secrets are referenced by ENV-VAR name only — never stored."""
    points = {
        "logosforge": IntegrationPoint(
            name="LOGOSFORGE — manuscript import",
            type=IntegrationPointType.LOGOSFORGE,
            status=IntegrationPointStatus.PLANNED,
            endpoint="logosforge://export/manuscripts",
            notes=(
                "Bridge to the separate LOGOSFORGE writing subsystem; pull "
                "finished drafts into SUPERVOID Publishing as manuscripts."
            ),
        ),
        "movies": IntegrationPoint(
            name="SUPERVOID Pictures — screen production",
            type=IntegrationPointType.SUPERVOID_MOVIES,
            status=IntegrationPointStatus.ACTIVE,
            endpoint="/api/screen",
            notes=(
                "Operational internal adapter. Promote a Work/graphic novel to "
                "an adaptation dossier, build a ScreenProject of scenes & shots "
                "(reusing storyboard panels), and export the adaptation package."
            ),
        ),
        "knowledge": IntegrationPoint(
            name="Archive / Knowledge Graph",
            type=IntegrationPointType.ARCHIVE_KNOWLEDGE_GRAPH,
            status=IntegrationPointStatus.ACTIVE,
            endpoint="/api/knowledge",
            notes="Editorial knowledge graph available in-app.",
        ),
        # --- operational hub adapters (local-first) ---
        "n8n": IntegrationPoint(
            name="n8n — automation webhook",
            type=IntegrationPointType.OTHER,
            status=IntegrationPointStatus.ACTIVE,
            adapter_key="n8n_webhook",
            endpoint="http://localhost:5678/webhook/supervoid",
            config={"webhook_url": "http://localhost:5678/webhook/supervoid"},
            credential_refs={"auth_token": "SUPERVOID_N8N_TOKEN"},
            notes="Outbound automation events; recorded unless network is enabled.",
        ),
        "comfyui": IntegrationPoint(
            name="ComfyUI — local generation",
            type=IntegrationPointType.AI_LAB,
            status=IntegrationPointStatus.ACTIVE,
            adapter_key="comfyui",
            endpoint="http://127.0.0.1:8188",
            config={"base_url": "http://127.0.0.1:8188"},
            notes="Queue workflows, attach outputs to assets with provenance.",
        ),
        "github": IntegrationPoint(
            name="GitHub — Silent Workshop repository",
            type=IntegrationPointType.OTHER,
            status=IntegrationPointStatus.ACTIVE,
            adapter_key="github_project",
            endpoint="https://github.com/supervoid/silent-workshop",
            config={"owner": "supervoid", "repo": "silent-workshop"},
            credential_refs={"token": "SUPERVOID_GITHUB_TOKEN"},
            notes="Link commits, issues and PRs to production tasks.",
        ),
        "affinity": IntegrationPoint(
            name="Affinity — file exchange",
            type=IntegrationPointType.OTHER,
            status=IntegrationPointStatus.ACTIVE,
            adapter_key="file_exchange.affinity",
            config={"discipline": "layout/illustration"},
            notes="Structured export/import packages for Affinity (no remote control).",
        ),
    }
    session.add_all(points.values())
    session.commit()
    for point in points.values():
        session.refresh(point)
    return points


def _entity(
    name: str, kind: EntityKind, description: str | None = None
) -> KnowledgeEntity:
    return KnowledgeEntity(
        name=name,
        slug=slugify(name),
        kind=kind,
        description=description,
    )


def _seed_knowledge_graph(
    session: Session, manuscripts: dict[str, Manuscript]
) -> None:
    """A small but coherent starter graph for the demo manuscripts."""

    entities = {
        "inland_seas": _entity(
            "Inland seas", EntityKind.THEME,
            "A recurring concern with closed, brackish bodies of water.",
        ),
        "memory": _entity(
            "Memory", EntityKind.THEME, "Personal and inherited remembrance."
        ),
        "labour": _entity(
            "Labour", EntityKind.THEME, "Daily work and the hands that do it."
        ),
        "letters": _entity("Letters", EntityKind.THEME, "Correspondence as form."),
        "archive": _entity(
            "Archive", EntityKind.THEME,
            "The collected paper trace of a life or institution.",
        ),
        "salt": _entity("Salt", EntityKind.MOTIF, "Saline as substance and image."),
        "type_design": _entity(
            "Type design", EntityKind.MOTIF, "The making and shaping of letterforms."
        ),
        "iberian_peninsula": _entity(
            "Iberian peninsula", EntityKind.PLACE,
            "Setting for several inland-sea essays.",
        ),
        "kyoto": _entity(
            "Kyoto", EntityKind.PLACE, "Capital and craft city of late-19th-century Japan."
        ),
        "early_twentieth_century": _entity(
            "Early twentieth century", EntityKind.PERIOD,
            "Pre-war provincial Europe, roughly 1900–1930.",
        ),
        "buffon": _entity(
            "Georges-Louis Leclerc de Buffon", EntityKind.PERSON,
            "Eighteenth-century French naturalist whose Histoire Naturelle "
            "shapes the natural-philosophy tradition.",
        ),
    }
    session.add_all(entities.values())
    session.commit()
    for e in entities.values():
        session.refresh(e)

    # A handful of typed edges between entities.
    relationships = [
        KnowledgeRelationship(
            source_id=entities["inland_seas"].id,
            target_id=entities["salt"].id,
            kind=RelationshipKind.RELATED_TO,
            weight=0.9,
        ),
        KnowledgeRelationship(
            source_id=entities["letters"].id,
            target_id=entities["memory"].id,
            kind=RelationshipKind.RELATED_TO,
            weight=0.7,
        ),
        KnowledgeRelationship(
            source_id=entities["archive"].id,
            target_id=entities["memory"].id,
            kind=RelationshipKind.RELATED_TO,
            weight=0.8,
        ),
        KnowledgeRelationship(
            source_id=entities["type_design"].id,
            target_id=entities["labour"].id,
            kind=RelationshipKind.RELATED_TO,
            weight=0.6,
        ),
        KnowledgeRelationship(
            source_id=entities["buffon"].id,
            target_id=entities["archive"].id,
            kind=RelationshipKind.INFLUENCES,
            weight=0.5,
            description="Buffon's classificatory impulse shapes the archive theme.",
        ),
    ]
    session.add_all(relationships)
    session.commit()

    # Manuscript ↔ entity links.
    links: list[ManuscriptEntityLink] = []

    def link(ms_key: str, entity_key: str, role: ManuscriptLinkRole, relevance: float = 0.7):
        links.append(
            ManuscriptEntityLink(
                manuscript_id=manuscripts[ms_key].id,
                entity_id=entities[entity_key].id,
                role=role,
                relevance=relevance,
            )
        )

    # The Salt Atlases — published essays on inland seas.
    link("salt_atlases", "inland_seas", ManuscriptLinkRole.TAGGED, 0.95)
    link("salt_atlases", "salt", ManuscriptLinkRole.TAGGED, 0.9)
    link("salt_atlases", "archive", ManuscriptLinkRole.TAGGED, 0.7)
    link("salt_atlases", "memory", ManuscriptLinkRole.TAGGED, 0.6)
    link("salt_atlases", "iberian_peninsula", ManuscriptLinkRole.SET_IN, 0.9)

    # Letters to a Dim Province — early-20th-century epistolary novel.
    link("letters_dim", "letters", ManuscriptLinkRole.TAGGED, 0.95)
    link("letters_dim", "memory", ManuscriptLinkRole.TAGGED, 0.8)
    link("letters_dim", "early_twentieth_century", ManuscriptLinkRole.SET_IN, 0.85)

    # Algebra of Birds — natural philosophy in the Buffon tradition.
    link("algebra_birds", "buffon", ManuscriptLinkRole.REFERENCES, 0.9)
    link("algebra_birds", "archive", ManuscriptLinkRole.TAGGED, 0.4)

    # Quintus, the Foundry — Kyoto typefounder novel.
    link("quintus", "type_design", ManuscriptLinkRole.TAGGED, 0.95)
    link("quintus", "labour", ManuscriptLinkRole.TAGGED, 0.7)
    link("quintus", "kyoto", ManuscriptLinkRole.SET_IN, 0.9)

    # The Silent Workshop — printer / binder correspondence.
    link("silent_workshop", "labour", ManuscriptLinkRole.TAGGED, 0.8)
    link("silent_workshop", "letters", ManuscriptLinkRole.TAGGED, 0.85)

    session.add_all(links)
    session.commit()


def _seed_public_reader(session: Session, works: dict[str, Work]) -> None:
    """Seed the public Graphic Novel Webviewer demo.

    Demonstrates the publication bridge (private Work -> PublishedWork shell)
    then curates the public-only volume/chapters/pages/media/hotspots by hand.
    Page images are local placeholder SVGs; audio/video are referenced
    placeholders the reader degrades over gracefully.
    """
    # Public media assets (audio/video). Page art is referenced by path on the
    # page rows, not as media-asset rows.
    theme = PublicMediaAsset(
        type=MediaAssetType.AUDIO,
        title="The Silent Workshop — Main Theme",
        file_path="/public/demo/audio/theme.mp3",
        loop=True,
        duration=180,
        credits="SUPERVOID Sound (placeholder)",
    )
    chapter_two_theme = PublicMediaAsset(
        type=MediaAssetType.AUDIO,
        title="Chapter II — Night Bindery",
        file_path="/public/demo/audio/chapter-2.mp3",
        loop=True,
        duration=200,
        credits="SUPERVOID Sound (placeholder)",
    )
    intro_video = PublicMediaAsset(
        type=MediaAssetType.VIDEO,
        title="The Silent Workshop — Intro",
        file_path="/public/demo/video/intro.mp4",
        poster_image="/public/demo/video/intro-poster.svg",
        duration=24,
        credits="SUPERVOID Motion (placeholder)",
    )
    hotspot_audio = PublicMediaAsset(
        type=MediaAssetType.AUDIO,
        title="Press cylinder (ambient)",
        file_path="/public/demo/audio/press.mp3",
        duration=12,
    )
    hotspot_video = PublicMediaAsset(
        type=MediaAssetType.VIDEO,
        title="Type being set",
        file_path="/public/demo/video/typesetting.mp4",
        poster_image="/public/demo/video/intro-poster.svg",
        duration=15,
    )
    session.add_all(
        [theme, chapter_two_theme, intro_video, hotspot_audio, hotspot_video]
    )
    session.commit()
    for asset in (theme, chapter_two_theme, intro_video, hotspot_audio, hotspot_video):
        session.refresh(asset)

    # Published work shell via the bridge (public metadata only), then curate.
    src = works.get("silent_workshop")
    if src is not None:
        pub = publish_work_to_public_reader(session, src.id)
    else:  # pragma: no cover - demo always has the graphic novel work
        pub = PublishedWork(slug="the-silent-workshop", title="The Silent Workshop")
        session.add(pub)
        session.commit()
        session.refresh(pub)

    pub.slug = "the-silent-workshop"
    pub.title = "The Silent Workshop"
    pub.subtitle = "A correspondence in ink"
    pub.public_synopsis = (
        "A printer and a binder write to each other for forty years and never "
        "meet — a quiet graphic novel about craft, distance, and the marks we "
        "leave on paper."
    )
    pub.cover_image = "/public/demo/covers/silent-workshop.svg"
    pub.status = PublishedStatus.PUBLISHED
    pub.publication_date = date.today() - timedelta(days=14)
    pub.author_credit = "Saoirse Carrick"
    pub.artist_credit = "Saoirse Carrick"
    pub.tags = ["graphic novel", "literary", "noir", "craft"]
    pub.music_track_id = theme.id
    pub.video_intro_id = intro_video.id
    # Listed in the public Bookshop (selling catalogue).
    pub.for_sale = True
    pub.price_cents = 2400
    pub.currency = "EUR"
    pub.format_label = "Hardcover · 96pp"
    pub.buy_url = "https://bookshop.org/"
    session.add(pub)
    session.commit()
    session.refresh(pub)

    volume = PublishedVolume(
        published_work_id=pub.id,
        title="Volume One",
        volume_number=1,
        public_description="Letters unsent, and the work that filled the silence.",
        cover_image="/public/demo/covers/silent-workshop-vol1.svg",
        publication_date=pub.publication_date,
        music_track_id=theme.id,
    )
    session.add(volume)
    session.commit()
    session.refresh(volume)

    chapter_one = PublishedChapter(
        published_volume_id=volume.id,
        title="The First Letter",
        chapter_number=1,
        public_description="An introduction in ink.",
        music_track_id=theme.id,
        video_intro_id=intro_video.id,
    )
    chapter_two = PublishedChapter(
        published_volume_id=volume.id,
        title="Night Bindery",
        chapter_number=2,
        public_description="Work after dark.",
        music_track_id=chapter_two_theme.id,
    )
    session.add_all([chapter_one, chapter_two])
    session.commit()
    for chapter in (chapter_one, chapter_two):
        session.refresh(chapter)

    def _page(chapter: PublishedChapter, n: int, **over) -> PublishedPage:
        return PublishedPage(
            published_chapter_id=chapter.id,
            page_number=n,
            image_path=f"/public/demo/pages/page-{n:03d}.svg",
            alt_text=f"The Silent Workshop, page {n}",
            width=1400,
            height=2000,
            **over,
        )

    pages = [
        _page(chapter_one, 1),
        _page(chapter_one, 2),
        _page(chapter_one, 3, video_overlay_id=intro_video.id),
        _page(chapter_two, 4, music_track_id=chapter_two_theme.id),
        _page(chapter_two, 5),
        _page(chapter_two, 6),
    ]
    session.add_all(pages)
    session.commit()
    for page in pages:
        session.refresh(page)

    hotspots = [
        PublicHotspot(
            published_page_id=pages[0].id, type=HotspotType.INFO,
            x=12, y=14, width=26, height=10, title="The Workshop",
            content="A jobbing print shop on a harbour street.",
        ),
        PublicHotspot(
            published_page_id=pages[0].id, type=HotspotType.CHARACTER,
            x=58, y=42, width=24, height=18, title="The Printer",
            content="Forty years at the same press; he never posted a reply.",
        ),
        PublicHotspot(
            published_page_id=pages[1].id, type=HotspotType.LOCATION,
            x=20, y=56, width=32, height=14, title="The Harbour",
            content="Where the letters were posted, and never answered.",
        ),
        PublicHotspot(
            published_page_id=pages[2].id, type=HotspotType.LORE,
            x=14, y=20, width=30, height=12, title="On Movable Type",
            content="A short note on setting type by hand, letter by letter.",
        ),
        PublicHotspot(
            published_page_id=pages[2].id, type=HotspotType.VIDEO,
            x=55, y=58, width=32, height=22, title="Watch: type being set",
            video_id=hotspot_video.id,
        ),
        PublicHotspot(
            published_page_id=pages[3].id, type=HotspotType.AUDIO,
            x=32, y=30, width=22, height=22, title="Listen: the press",
            audio_track_id=hotspot_audio.id,
        ),
        PublicHotspot(
            published_page_id=pages[4].id, type=HotspotType.EXTERNAL_LINK,
            x=40, y=70, width=28, height=10, title="About SUPERVOID",
            target_url="https://example.invalid/supervoid",
        ),
    ]
    session.add_all(hotspots)
    session.commit()

    # Public cinematic panels (normalised coords) for the first two pages — this
    # drives real panel-by-panel reading. A panel-scoped hotspot rides page 1.
    panels = [
        PublishedPanel(
            published_page_id=pages[0].id, panel_number=1, reading_order=0,
            x=0.06, y=0.05, width=0.88, height=0.42,
            transition=PanelTransition.FADE, transition_duration_ms=700,
            caption="The workshop wakes; the press is cold.",
            alt_text="Wide establishing panel of the print workshop at dawn.",
        ),
        PublishedPanel(
            published_page_id=pages[0].id, panel_number=2, reading_order=1,
            x=0.10, y=0.52, width=0.80, height=0.42,
            focus_x=0.30, focus_y=0.55, focus_width=0.40, focus_height=0.35,
            transition=PanelTransition.DISSOLVE, transition_duration_ms=900,
            caption="“Still nothing,” he says, to no one.",
            alt_text="Close panel on the printer at the bench.",
            audio_track_id=hotspot_audio.id,
        ),
        PublishedPanel(
            published_page_id=pages[3].id, panel_number=1, reading_order=0,
            x=0.05, y=0.08, width=0.90, height=0.84,
            transition=PanelTransition.CUT, transition_duration_ms=400,
            caption="Night bindery: thread, glue, and lamplight.",
        ),
    ]
    session.add_all(panels)
    session.commit()
    for panel in panels:
        session.refresh(panel)
    session.add(PublicHotspot(
        published_page_id=pages[0].id, published_panel_id=panels[1].id,
        type=HotspotType.LORE, x=34, y=58, width=28, height=20,
        title="On the unanswered letter",
        content="The letter on the bench is never opened on-page.",
    ))

    # Publication history + an approved publication request (the demo work is
    # already PUBLISHED). Preserves an auditable lifecycle.
    admin = session.exec(select(User).where(User.email == "helena.pryce@supervoid.local")).first()
    actor_id = admin.id if admin else None
    validation = {"ok": True, "errors": 0, "warnings": 0, "issues": []}
    session.add(PublicationApproval(
        published_work_id=pub.id, status=PublicationApprovalStatus.APPROVED,
        requested_by_id=actor_id, decided_by_id=actor_id, decided_at=utcnow(),
        validation=validation, note="Cleared for the demo launch.",
    ))
    session.add_all([
        PublicationEvent(published_work_id=pub.id, action=PublicationAction.CREATED, actor_id=actor_id),
        PublicationEvent(
            published_work_id=pub.id, action=PublicationAction.APPROVED, actor_id=actor_id,
        ),
        PublicationEvent(
            published_work_id=pub.id, action=PublicationAction.PUBLISHED, actor_id=actor_id,
            from_status=PublishedStatus.DRAFT, to_status=PublishedStatus.PUBLISHED,
        ),
    ])
    session.commit()


def _seed_transmedia(
    session: Session,
    works: dict[str, Work],
    authors: dict[str, Author],
) -> None:
    """Seed the IP / transmedia layer above Work: a story world with a series,
    Works placed into it across divisions, and an adaptation dossier."""
    world = StoryWorld(
        name="The Silent Workshop",
        slug="the-silent-workshop",
        description=(
            "An intimate universe of printers, binders and the letters that "
            "pass between them — SUPERVOID's flagship craft-noir property."
        ),
        canon_summary=(
            "Canon follows the printer Anselm and the binder he never meets. "
            "The graphic novel is primary canon; screen treatments are "
            "alternate-canon explorations."
        ),
        status=StoryWorldStatus.ACTIVE,
        visual_identity_notes=(
            "Greyscale wash, brass accents, hand-set type motifs; quiet, "
            "archival, never neon."
        ),
        default_language="en",
        owner_id=authors["carrick"].id,
    )
    session.add(world)
    session.commit()
    session.refresh(world)

    series = StorySeries(
        story_world_id=world.id,
        title="The Workshop Cycle",
        description="The core sequence of Silent Workshop stories.",
        sequence_order=1,
        status=StorySeriesStatus.ONGOING,
    )
    session.add(series)
    session.commit()
    session.refresh(series)

    # Place the graphic novel as primary canon in the world/series.
    gn = works["silent_workshop"]
    gn.story_world_id = world.id
    gn.story_series_id = series.id
    gn.series_order = 1
    gn.primary_division = StudioDivision.PUBLISHING
    gn.primary_medium = Medium.GRAPHIC_NOVEL
    gn.canon_status = CanonState.CANON
    session.add(gn)

    # The screen-treatment Work is an alternate-canon pictures Work derived
    # from the graphic novel.
    screen = works["workshop_screen"]
    screen.story_world_id = world.id
    screen.primary_division = StudioDivision.PICTURES
    screen.primary_medium = Medium.FILM
    screen.canon_status = CanonState.ALTERNATE
    screen.source_work_id = gn.id
    session.add(screen)
    session.commit()

    dossier = AdaptationDossier(
        source_work_id=gn.id,
        target_work_id=screen.id,
        target_medium=Medium.FILM,
        target_division=StudioDivision.PICTURES,
        status=AdaptationStatus.IN_DEVELOPMENT,
        logline=(
            "A printer's forty-year correspondence becomes a feature about "
            "distance, craft, and the marks we leave on paper."
        ),
        format="Feature film",
        intended_scope="~110 minutes",
        rights_clearance=RightsClearanceState.IN_PROGRESS,
        creative_notes=(
            "Hold to the greyscale palette; the unanswered letters are the "
            "spine. Explore a near-silent first act."
        ),
        source_revision="Graphic novel v1",
    )
    session.add(dossier)
    session.commit()


def _seed_collaboration(
    session: Session,
    users: dict[str, User],
    works: dict[str, Work],
) -> None:
    """Seed project-scoped collaboration: memberships on the Silent Workshop
    story world (which cascade to its works) and on the graphic-novel Work
    itself, plus the audit trail those changes produce.

    Demonstrates the layering: ``UserRole`` still governs studio-wide actions,
    while these memberships grant access to specific projects.
    """
    world = session.exec(
        select(StoryWorld).where(StoryWorld.slug == "the-silent-workshop")
    ).first()
    gn = works.get("silent_workshop")

    def _membership(
        user: User,
        role: ProjectRole,
        *,
        work_id: str | None = None,
        story_world_id: str | None = None,
        status: MembershipStatus = MembershipStatus.ACTIVE,
        created_by: User | None = None,
        notes: str | None = None,
    ) -> ProjectMembership:
        m = ProjectMembership(
            user_id=user.id,
            work_id=work_id,
            story_world_id=story_world_id,
            role=role,
            status=status,
            accepted_at=(utcnow() if status == MembershipStatus.ACTIVE else None),
            created_by_id=created_by.id if created_by else None,
            notes=notes,
        )
        session.add(m)
        session.flush()
        policy.record_audit(
            session,
            action=MembershipAuditAction.INVITED,
            subject_user_id=user.id,
            actor_id=created_by.id if created_by else None,
            membership=m,
            role=role,
            to_status=MembershipStatus.INVITED,
        )
        if status == MembershipStatus.ACTIVE:
            policy.record_audit(
                session,
                action=MembershipAuditAction.ACCEPTED,
                subject_user_id=user.id,
                actor_id=user.id,
                membership=m,
                from_status=MembershipStatus.INVITED,
                to_status=MembershipStatus.ACTIVE,
            )
        return m

    admin = users["helena"]

    if world is not None:
        # World-level memberships cascade to every Work in the world.
        _membership(
            users["cecilia"], ProjectRole.OWNER,
            story_world_id=world.id, created_by=admin,
            notes="World lead for the Silent Workshop property.",
        )
        _membership(
            users["kazu"], ProjectRole.PRODUCTION_MANAGER,
            story_world_id=world.id, created_by=admin,
        )

    if gn is not None:
        # Work-level memberships, scoped to the graphic novel only.
        _membership(
            users["jonas"], ProjectRole.EDITOR,
            work_id=gn.id, created_by=users["cecilia"],
        )
        _membership(
            users["mireille"], ProjectRole.MARKETING,
            work_id=gn.id, created_by=users["cecilia"],
        )
        # A still-pending invitation, to show the INVITED state in the UI.
        _membership(
            users["bartholomew"], ProjectRole.REVIEWER,
            work_id=gn.id, status=MembershipStatus.INVITED,
            created_by=users["cecilia"],
            notes="Structural review pass — invitation pending.",
        )

    session.commit()


def _seed_production_tasks(
    session: Session,
    works: dict[str, Work],
    users: dict[str, User],
) -> None:
    """Seed the general production task system by applying the graphic-novel
    template to the flagship Work, then assigning a few tasks, advancing one,
    and opening a human approval request on the deliverable."""
    gn = works.get("silent_workshop")
    if gn is None:  # pragma: no cover - demo always has the graphic novel
        return

    template = production_templates.get_template("graphic_novel_volume")
    if template is None:  # pragma: no cover
        return
    result = production_templates.instantiate_template(
        session, template, work_id=gn.id, actor_id=users["helena"].id
    )
    session.commit()

    tasks = [session.get(ProductionItem, tid) for tid in result.task_ids]
    by_title = {t.title: t for t in tasks if t is not None}

    # Assign a few tasks across people.
    assignments = {
        "Write script": users["cecilia"],
        "Thumbnails / layouts": users["kazu"],
        "Pencils": users["kazu"],
        "Cover art": users["ines"],
    }
    for title, person in assignments.items():
        task = by_title.get(title)
        if task is not None:
            task.assignee_id = person.id
            task.reviewer_id = users["jonas"].id
            session.add(task)
    session.commit()

    # Advance the script through a couple of legal transitions.
    script = by_title.get("Write script")
    if script is not None:
        production_service.apply_transition(
            session, script, ProductionItemStatus.IN_PROGRESS,
            actor_id=users["cecilia"].id,
        )
        session.commit()

    # Open a human approval request on the print deliverable.
    deliverable = by_title.get("Print run")
    if deliverable is not None:
        approval = ApprovalRequest(
            requested_by_id=users["kazu"].id,
            approver_id=users["helena"].id,
            task_id=deliverable.id,
            target_type="production_item",
            target_id=deliverable.id,
            title="Approve print files",
            description="Final files ready for the printer — needs sign-off.",
        )
        session.add(approval)
        session.commit()


def _seed_asset_library(
    session: Session,
    works: dict[str, Work],
    authors: dict[str, Author],
    users: dict[str, User],
) -> None:
    """Seed the central Asset Library: a versioned cover asset with provenance
    and a licence, plus a human-made character design — wired to the flagship
    Work. Assets are private and never surface in the public reader."""
    gn = works.get("silent_workshop")
    world = session.exec(
        select(StoryWorld).where(StoryWorld.slug == "the-silent-workshop")
    ).first()
    if gn is None:  # pragma: no cover - demo always has the graphic novel
        return

    # --- Cover asset, two versions, v2 current (v1 superseded) ---
    cover = Asset(
        title="The Silent Workshop — Cover",
        asset_type=AssetType.COVER,
        work_id=gn.id,
        story_world_id=world.id if world is not None else None,
        canon_status=CanonState.CANON,
        visibility=AssetVisibility.PUBLIC_CANDIDATE,
        owner_id=users["kazu"].id,
        tags=["cover", "key-art", "noir"],
        description="Front cover art for Volume One.",
    )
    session.add(cover)
    session.flush()

    v1 = AssetVersion(
        asset_id=cover.id,
        version_number=1,
        storage_key=f"placeholder:{cover.id}-v1",
        mime_type="image/png",
        size_bytes=2_400_000,
        checksum="0" * 64,
        width=1400,
        height=2100,
        creator_id=users["kazu"].id,
        approval_status=AssetApprovalStatus.SUPERSEDED,
    )
    v2 = AssetVersion(
        asset_id=cover.id,
        version_number=2,
        storage_key=f"placeholder:{cover.id}-v2",
        mime_type="image/png",
        size_bytes=2_550_000,
        checksum="1" * 64,
        width=1400,
        height=2100,
        creator_id=users["kazu"].id,
        approval_status=AssetApprovalStatus.APPROVED,
        notes="Tightened contrast; final title treatment.",
    )
    session.add_all([v1, v2])
    session.flush()
    v1.superseded_by_id = v2.id
    cover.current_version_id = v2.id
    session.add_all([v1, cover])

    # Provenance on the current version: AI-assisted, human-finished.
    session.add(
        ProvenanceRecord(
            asset_version_id=v2.id,
            kind=ProvenanceKind.AI_ASSISTED,
            provider="local",
            base_model="SUPERVOID-Diffusion",
            base_model_version="1.5",
            adapter_identifiers="lora:silent-workshop-style",
            prompt="a print workshop at night, brass and ink, noir lighting",
            negative_prompt="text, watermark",
            seed=20260614,
            sampler="dpmpp_2m",
            settings={"steps": 30, "cfg_scale": 6.5},
            human_modifications="Repainted hands; hand-set the title typography.",
            generation_date=utcnow() - timedelta(days=10),
            responsible_user_id=users["kazu"].id,
            commercial_use_review=CommercialUseReviewStatus.CLEARED,
        )
    )

    # Licence on the asset (commissioned, in-house, expiring to demo warnings).
    session.add(
        LicenceRecord(
            asset_id=cover.id,
            rights_holder="SUPERVOID Publishing",
            licence_type=LicenceType.COMMISSIONED,
            source="In-house art direction",
            territory="World",
            permitted_uses="Cover, marketing, editions.",
            attribution_requirements="None (work for hire).",
            expiration_date=date.today() + timedelta(days=20),
            review_state=LicenceReviewState.APPROVED,
        )
    )

    # Link the cover to the work.
    session.add(
        AssetLink(
            asset_id=cover.id,
            asset_version_id=v2.id,
            target_type=AssetLinkTargetType.WORK,
            target_id=gn.id,
            role="cover",
        )
    )

    # --- A purely human-made character design ---
    design = Asset(
        title="Anselm — Character Design",
        asset_type=AssetType.CHARACTER_DESIGN,
        work_id=gn.id,
        story_world_id=world.id if world is not None else None,
        canon_status=CanonState.CANON,
        visibility=AssetVisibility.INTERNAL,
        owner_id=users["cecilia"].id,
        tags=["character", "model-sheet"],
        description="Turnaround and expressions for the printer, Anselm.",
    )
    session.add(design)
    session.flush()
    dv1 = AssetVersion(
        asset_id=design.id,
        version_number=1,
        storage_key=f"placeholder:{design.id}-v1",
        mime_type="image/png",
        size_bytes=1_800_000,
        checksum="2" * 64,
        creator_id=users["cecilia"].id,
        approval_status=AssetApprovalStatus.APPROVED,
    )
    session.add(dv1)
    session.flush()
    design.current_version_id = dv1.id
    session.add(design)
    session.add(
        ProvenanceRecord(
            asset_version_id=dv1.id,
            kind=ProvenanceKind.HUMAN_CREATED,
            human_modifications="Hand-drawn, inked and scanned.",
            responsible_user_id=users["cecilia"].id,
            commercial_use_review=CommercialUseReviewStatus.CLEARED,
        )
    )
    session.commit()


def _seed_graphic_novel_hierarchy(
    session: Session,
    works: dict[str, Work],
) -> None:
    """Seed a small but complete production breakdown for the flagship graphic
    novel: volume → chapter → sequence → pages → panels → elements, with
    knowledge-graph entity links (no character/location duplication) and a
    storyboard↔final comparison. Rolls up into the summary at the end."""
    gn_work = works.get("silent_workshop")
    if gn_work is None:  # pragma: no cover
        return
    production = session.exec(
        select(GraphicNovelProduction).where(
            GraphicNovelProduction.work_id == gn_work.id
        )
    ).first()
    if production is None:  # pragma: no cover
        return

    # Knowledge-graph entities the panels reference (characters / locations).
    def _entity(name: str, kind: EntityKind) -> KnowledgeEntity:
        slug = slugify(name)
        existing = session.exec(
            select(KnowledgeEntity).where(KnowledgeEntity.slug == slug)
        ).first()
        if existing is not None:
            return existing
        ent = KnowledgeEntity(name=name, slug=slug, kind=kind)
        session.add(ent)
        session.flush()
        return ent

    anselm = _entity("Anselm the Printer", EntityKind.CHARACTER)
    workshop = _entity("The Workshop", EntityKind.PLACE)

    # The cover asset's versions, for the storyboard↔final comparison demo.
    cover = session.exec(
        select(Asset).where(Asset.title == "The Silent Workshop — Cover")
    ).first()
    cover_versions = sorted(cover.versions, key=lambda v: v.version_number) if cover else []
    storyboard_v = cover_versions[0].id if len(cover_versions) > 0 else None
    final_v = cover_versions[1].id if len(cover_versions) > 1 else None

    volume = GraphicNovelVolume(
        production_id=production.id, volume_number=1, title="Volume One",
        status=GNStatus.IN_PROGRESS, position=0,
    )
    session.add(volume)
    session.flush()
    chapter = GraphicNovelChapter(
        volume_id=volume.id, chapter_number=1, title="The First Letter",
        status=GNStatus.IN_PROGRESS, position=0,
    )
    session.add(chapter)
    session.flush()
    sequence = GraphicNovelSequence(
        chapter_id=chapter.id, sequence_number=1, title="Night at the press",
        status=GNStatus.IN_PROGRESS, position=0,
    )
    session.add(sequence)
    session.flush()

    # Page 1 — well advanced; print geometry set.
    page1 = GraphicNovelPage(
        sequence_id=sequence.id, page_number=1, position=0, status=GNStatus.COMPLETE,
        page_side=PageSide.SINGLE,
        script="Anselm sets the last line of type as the harbour bell rings.",
        visual_brief="Warm key light from the press lamp; deep shadow.",
        dialogue_summary="Anselm reflects on forty years of unanswered letters.",
        lettering_status=StreamStatus.COMPLETE,
        colour_status=StreamStatus.COMPLETE,
        final_status=StreamStatus.COMPLETE,
        print_width_mm=170, print_height_mm=240, bleed_mm=3, safe_area_mm=5,
        master_asset_id=cover.id if cover else None,
    )
    # Page 2 — in progress.
    page2 = GraphicNovelPage(
        sequence_id=sequence.id, page_number=2, position=1, status=GNStatus.IN_PROGRESS,
        page_side=PageSide.SINGLE,
        script="A reply that never comes; the press falls silent.",
        lettering_status=StreamStatus.IN_PROGRESS,
        colour_status=StreamStatus.PENDING,
        final_status=StreamStatus.NOT_PLANNED,
        print_width_mm=170, print_height_mm=240, bleed_mm=3, safe_area_mm=5,
    )
    session.add_all([page1, page2])
    session.flush()

    # Panels on page 1.
    p1 = GraphicNovelPanel(
        page_id=page1.id, panel_number=1, position=0, status=GNStatus.COMPLETE,
        x=0.05, y=0.05, width=0.9, height=0.45,
        script_beat="Establishing the workshop at night.",
        captions="Forty winters at the same press.",
        camera_framing=CameraFraming.ESTABLISHING, camera_angle=CameraAngle.HIGH,
        approval_status=AssetApprovalStatus.APPROVED,
        storyboard_asset_version_id=storyboard_v,
        final_asset_version_id=final_v,
    )
    p2 = GraphicNovelPanel(
        page_id=page1.id, panel_number=2, position=1, status=GNStatus.COMPLETE,
        x=0.05, y=0.52, width=0.43, height=0.43,
        dialogue="“Still nothing.”",
        camera_framing=CameraFraming.CLOSE_UP, camera_angle=CameraAngle.EYE_LEVEL,
    )
    session.add_all([p1, p2])
    session.flush()

    # Panel elements: character + location (entity refs) + a caption text.
    session.add_all([
        GraphicNovelPanelElement(
            panel_id=p1.id, element_type=PanelElementType.LOCATION,
            entity_id=workshop.id, position=0,
        ),
        GraphicNovelPanelElement(
            panel_id=p2.id, element_type=PanelElementType.CHARACTER,
            entity_id=anselm.id, position=0, x=0.2, y=0.2, width=0.5, height=0.7,
        ),
        GraphicNovelPanelElement(
            panel_id=p2.id, element_type=PanelElementType.TEXT,
            text_content="Still nothing.", label="dialogue", position=1,
        ),
    ])

    # Page-level entity links (characters/locations on the page).
    session.add_all([
        GraphicNovelPageEntityLink(page_id=page1.id, entity_id=anselm.id, role="lead"),
        GraphicNovelPageEntityLink(page_id=page1.id, entity_id=workshop.id, role="setting"),
    ])
    session.flush()

    # Roll the detailed statuses up into the high-level summary.
    gn_service.recalculate_production(session, production)
    session.commit()


def _seed_screen_pictures(
    session: Session,
    works: dict[str, Work],
) -> None:
    """Seed the SUPERVOID Pictures bounded context: a ScreenProject created from
    the (approved) Silent Workshop adaptation dossier, with a scene, two shots —
    one mapping a graphic-novel storyboard panel — and a character link."""
    gn = works.get("silent_workshop")
    if gn is None:  # pragma: no cover
        return
    dossier = session.exec(
        select(AdaptationDossier).where(AdaptationDossier.source_work_id == gn.id)
    ).first()
    if dossier is None:  # pragma: no cover
        return
    if not screen_service.is_dossier_approved(dossier):
        dossier.status = AdaptationStatus.IN_DEVELOPMENT
        session.add(dossier)
        session.flush()

    project = screen_service.create_project_from_dossier(
        session, dossier, fmt=ScreenFormat.FILM,
        title="The Silent Workshop — Feature",
    )
    project.synopsis = (
        "A near-silent feature about a printer's forty-year correspondence."
    )
    session.add(project)
    session.flush()

    unit = project.units[0]
    sequence = ScreenSequence(
        unit_id=unit.id, sequence_number=1, title="Night at the press", position=0,
    )
    session.add(sequence)
    session.flush()

    scene = Scene(
        sequence_id=sequence.id, scene_number=1, position=0,
        heading="INT. THE WORKSHOP — NIGHT",
        location="The Workshop", environment=SceneEnvironment.INT,
        time_of_day=SceneTimeOfDay.NIGHT,
        synopsis="Anselm sets the last line of type as the harbour bell rings.",
        script_text="The press lamp throws a long shadow. ANSELM works alone.",
        estimated_duration_seconds=180,
        continuity_notes="Ink-stained apron; the unanswered letter on the bench.",
    )
    session.add(scene)
    session.flush()

    # Character link to the knowledge entity (no duplication).
    anselm = session.exec(
        select(KnowledgeEntity).where(KnowledgeEntity.slug == "anselm-the-printer")
    ).first()
    if anselm is not None:
        session.add(
            SceneCharacterLink(scene_id=scene.id, entity_id=anselm.id, role="lead")
        )

    # Two shots; the first reuses a graphic-novel panel as its storyboard.
    panel = session.exec(select(GraphicNovelPanel)).first()
    shot1 = Shot(
        scene_id=scene.id, shot_number=1, position=0,
        framing=CameraFraming.ESTABLISHING, camera_angle=CameraAngle.HIGH,
        movement=ShotMovement.CRANE, lens="24mm", duration_seconds=12,
        blocking="Crane down from the rafters to the press.",
        lighting="Single warm key from the press lamp.",
        sound="Bell; the rhythm of the press.",
        source_storyboard_panel_id=panel.id if panel is not None else None,
    )
    shot2 = Shot(
        scene_id=scene.id, shot_number=2, position=1,
        framing=CameraFraming.CLOSE_UP, camera_angle=CameraAngle.EYE_LEVEL,
        movement=ShotMovement.STATIC, lens="85mm", duration_seconds=6,
        dialogue="“Still nothing.”",
        vfx="Subtle ink-bloom on the unanswered letter.",
    )
    session.add_all([shot1, shot2])
    session.flush()
    if panel is not None:
        session.add(ScreenShotPanelLink(shot_id=shot1.id, panel_id=panel.id, role="storyboard"))

    session.commit()


def _seed_agents(
    session: Session,
    manuscripts: dict[str, Manuscript],
    works: dict[str, Work],
    users: dict[str, User],
) -> None:
    """Seed the supervised studio-agent framework: a read-only analysis run
    (immediate findings), a propose-only run (a pending, human-gated proposal),
    and a versioned prompt template. Runs go through the real (dry-run) runner."""
    admin = users["helena"]

    consistency = agent_svc.get_agent("manuscript_consistency")
    ms = manuscripts.get("quintus")
    if consistency is not None and ms is not None:
        agent_svc.run_agent(
            session, definition=consistency, user=admin,
            target_type="manuscript", target_id=ms.id,
        )

    advisor = agent_svc.get_agent("work_metadata_advisor")
    work = works.get("quintus")
    if advisor is not None and work is not None:
        agent_svc.run_agent(
            session, definition=advisor, user=admin,
            target_type="work", target_id=work.id,
        )
    session.commit()

    template = PromptTemplate(
        key="manuscript.summary",
        name="Manuscript summary",
        description="System prompt for the editorial summary feature.",
        current_version=1,
    )
    session.add(template)
    session.flush()
    session.add(PromptTemplateVersion(
        template_id=template.id, version=1, created_by_id=admin.id,
        body="You are an editorial assistant. Summarise the manuscript faithfully.",
        notes="Initial version.",
    ))
    session.commit()


def _seed_integration_activity(
    session: Session,
    points: dict[str, IntegrationPoint],
    users: dict[str, User],
) -> None:
    """Seed the operational hub: an immediate read-only ComfyUI status read; a
    GitHub commit linked to a production task (requested → approved → executed);
    and a pending-approval n8n webhook event still awaiting sign-off — showing
    the approval boundary every external mutation passes through."""
    admin = users["helena"]

    comfy = points.get("comfyui")
    if comfy is not None:
        # Read-only: runs immediately, degrades gracefully (ComfyUI not assumed up).
        integration_hub.request_operation(
            session, comfy, "query_status", {"prompt_id": "demo-0001"},
            user=admin, dry_run=False,
        )
        session.commit()

    github = points.get("github")
    task = session.exec(select(ProductionItem)).first()
    if github is not None and task is not None:
        run = integration_hub.request_operation(
            session, github, "link_commit",
            {
                "external_ref": "a1b2c3d",
                "title": "Set the last line of type",
                "target_id": task.id,
            },
            user=admin, dry_run=False,
        )
        session.commit()
        session.refresh(run)
        integration_hub.approve_run(session, run, user=admin)
        session.commit()
        integration_hub.execute_run(session, run, user=admin)
        session.commit()

    n8n = points.get("n8n")
    if n8n is not None:
        # External: created PENDING_APPROVAL; nothing dispatched.
        integration_hub.request_operation(
            session, n8n, "send_event",
            {"event_type": "work.published", "data": {"title": "The Silent Workshop"}},
            user=admin, dry_run=False,
        )
        session.commit()


def _seed_business_layer(
    session: Session,
    works: dict[str, Work],
    manuscripts: dict[str, Manuscript],
    users: dict[str, User],
) -> None:
    """Seed the operational business layer: rights depth (windows, an option,
    chain of title, evidence, a status change), a small CRM (a publisher, a
    reviewer with a role/tag/interaction/opportunity), and an edition with two
    generated, validated distribution packages."""
    today = date.today()
    salt = works.get("salt_atlases")
    if salt is None:  # pragma: no cover
        return

    # --- Part A: deepen the existing Salt Atlases (World/English) rights ---
    rights = session.exec(
        select(Rights).where(Rights.work_id == salt.id, Rights.language == "English")
    ).first()
    if rights is not None:
        rights.rights_holder = "SUPERVOID Publishing"
        rights.exclusivity = RightsExclusivity.EXCLUSIVE
        rights.term_start_date = today - timedelta(days=400)
        rights.term_end_date = today + timedelta(days=365 * 6)
        rights.sublicensable = True
        rights.sublicense_terms = "Translation sublicensing permitted with approval."
        rights.reversion_conditions = "Rights revert if out of print for 18 months."
        rights.reversion_date = today + timedelta(days=365 * 6 + 30)
        rights.adaptation_constraints = "Film/TV reserved; no AI-generated derivatives."
        rights.territory_coverage = ["World"]
        rights.language_coverage = ["English"]
        rights.reminder_date = today + timedelta(days=45)
        session.add(rights)
        session.add(RightsWindow(
            rights_id=rights.id, scope=RightScope.PRINT, territory="World",
            language="English", exclusivity=RightsExclusivity.EXCLUSIVE,
            starts_on=today - timedelta(days=400),
            ends_on=today + timedelta(days=365 * 6),
            status=RightsWindowStatus.ACTIVE,
        ))
        session.add(RightsOption(
            rights_id=rights.id, label="Film option — Lantern Pictures",
            scope=RightScope.FILM, holder="Lantern Pictures",
            option_start=today - timedelta(days=30),
            option_end=today + timedelta(days=150),
            exercise_deadline=today + timedelta(days=120),
            fee=Decimal("5000.00"), currency="EUR",
            status=OptionPeriodStatus.OPEN,
        ))
        session.add(ChainOfTitleEntry(
            rights_id=rights.id, position=0, entry_type=ChainOfTitleType.CREATION,
            from_party="Iris Aldoria (author)", to_party="SUPERVOID Publishing",
            effective_date=today - timedelta(days=400),
            instrument="Head publishing agreement",
        ))
        session.add(RightsEvidence(
            rights_id=rights.id, kind=RightsEvidenceKind.CONTRACT,
            title="Signed publishing agreement", document_ref="contracts/salt-atlases.pdf",
            dated_on=today - timedelta(days=400),
        ))
        session.add(RightsStatusHistory(
            rights_id=rights.id, scope=RightScope.PRINT,
            from_status=RightStatus.AVAILABLE, to_status=RightStatus.LICENSED,
            note="Print licensed for the world English edition.",
            changed_by_id=users["helena"].id,
        ))

    # --- Part B: relationship memory (CRM) ---
    org = Organization(
        name="Éditions du Phare", kind=OrganizationKind.PUBLISHER, country="France",
        city="Paris", website="https://example.invalid/phare",
        source_of_introduction="Frankfurt Book Fair 2025",
        notes="French-language partner; interested in translations.",
    )
    session.add(org)
    session.flush()

    contact = Contact(
        full_name="Camille Lefevre", organization_id=org.id,
        title="Senior Reviews Editor", email="camille.lefevre@example.invalid",
        country="France", source_of_introduction="Introduced by Mireille Vance",
        interests=["literary non-fiction", "maps", "translation"],
        relevant_work_ids=[salt.id], follow_up_date=today + timedelta(days=14),
        consent_status=ConsentStatus.GRANTED, preferred_channel="email",
        consent_notes="Opted in to review copies at Frankfurt.",
    )
    session.add(contact)
    session.flush()
    session.add(ContactRole(
        contact_id=contact.id, role=ContactRoleKind.REVIEWER,
        organization_id=org.id, title="Reviews Editor", is_primary=True,
    ))
    session.add(ContactRole(
        contact_id=contact.id, role=ContactRoleKind.JOURNALIST, organization_id=org.id,
    ))
    tag = ContactTag(name="VIP", slug=_slugify_tag("VIP"), color="#b08")
    session.add(tag)
    session.flush()
    session.add(ContactTagLink(contact_id=contact.id, tag_id=tag.id))
    session.add(Interaction(
        contact_id=contact.id, organization_id=org.id,
        kind=InteractionKind.MEETING, direction=InteractionDirection.OUTBOUND,
        subject="Frankfurt — review & translation interest",
        body="Met at the fair; keen on the Salt Atlases for a French co-edition.",
        work_id=salt.id, follow_up_date=today + timedelta(days=14),
        created_by_id=users["mireille"].id,
    ))
    session.add(Opportunity(
        title="French co-edition — The Salt Atlases", kind=OpportunityKind.CO_EDITION,
        status=OpportunityStatus.QUALIFIED, organization_id=org.id,
        contact_id=contact.id, work_id=salt.id, value=Decimal("8000.00"),
        currency="EUR", expected_close_date=today + timedelta(days=90),
        source="Frankfurt Book Fair 2025", owner_id=users["mireille"].id,
    ))

    # --- Part C: an edition + two validated distribution packages ---
    ms = manuscripts.get("salt_atlases")
    edition = Edition(
        work_id=salt.id, manuscript_id=ms.id if ms else None,
        title="The Salt Atlases", format=EditionFormat.TRADE_PAPERBACK,
        language="en", territory="World", imprint="SUPERVOID Editions",
        identifier="9780306406157", identifier_type=EditionIdentifierType.ISBN_13,
        trim_size="6x9in", page_count=288, price=Decimal("24.00"), currency="USD",
        publication_date=today - timedelta(days=30),
        distribution_status=DistributionStatus.LIVE,
        files=[
            {"role": "cover", "asset_id": None, "path": "editions/salt/cover.pdf"},
            {"role": "interior", "path": "editions/salt/interior.pdf"},
        ],
        edition_metadata={
            "description": "A literary atlas of Europe's inland seas.",
            "keywords": ["atlas", "essays", "geography", "maps"],
            "categories": ["NAT045030", "TRV026000"],
            "author_bio": "Iris Aldoria is an essayist and cartographer.",
            "press_contact": "press@supervoid.local",
        },
    )
    session.add(edition)
    session.flush()
    for channel in (DistributionChannel.ONIX, DistributionChannel.PRESS_KIT):
        distribution_svc.generate_package(
            session, edition, channel, user=users["mireille"]
        )

    session.commit()


def run() -> None:
    init_db()
    with Session(engine) as session:
        if session.exec(select(User)).first() is not None:
            print("Seed skipped: database already populated.")
            return

        users = _seed_users(session)
        authors = _seed_authors(session)
        manuscripts = _seed_manuscripts(session, authors)
        works = _seed_works(session, authors, manuscripts)
        _seed_workflow_events(session, manuscripts, users)
        _seed_reviews(session, manuscripts, works, users)
        _seed_contracts(session, manuscripts, works, authors)
        _seed_rights(session, works)
        _seed_graphic_novel_production(session, works)
        _seed_production_items(session, manuscripts, works, users)
        _seed_editorial_notes(session, manuscripts, works, authors, users)
        _seed_production_records(session, manuscripts)
        _seed_calendar_events(session, works)
        integration_points = _seed_integration_points(session)
        _seed_knowledge_graph(session, manuscripts)
        _seed_public_reader(session, works)
        _seed_transmedia(session, works, authors)
        _seed_collaboration(session, users, works)
        _seed_production_tasks(session, works, users)
        _seed_asset_library(session, works, authors, users)
        _seed_graphic_novel_hierarchy(session, works)
        _seed_screen_pictures(session, works)
        _seed_agents(session, manuscripts, works, users)
        _seed_integration_activity(session, integration_points, users)
        _seed_business_layer(session, works, manuscripts, users)

    print(
        "Seeded SUPERVOID Publishing: "
        f"{len(users)} users (password '{DEMO_PASSWORD}' for all), "
        f"{len(authors)} authors, {len(works)} works, "
        f"{len(manuscripts)} manuscripts, "
        "with reviews, workflow events, contracts, rights, a graphic-novel "
        "production board, production items, production records, notes, "
        "calendar events, integration points, a starter knowledge graph, "
        "a public Graphic Novel Webviewer demo (1 published work, 1 volume, "
        "2 chapters, 6 pages, media + hotspots), the IP/transmedia layer "
        "(1 story world, 1 series, an adaptation dossier), project "
        "collaboration (5 memberships across a world and a work, with an "
        "audit trail), and a production task breakdown (graphic-novel template "
        "applied: milestones, tasks, dependencies, and a pending approval), and "
        "the Asset Library (a versioned cover with provenance + a near-expiry "
        "licence, plus a human-made character design), and a graphic-novel "
        "production hierarchy (1 volume → chapter → sequence → 2 pages → panels "
        "with knowledge-entity links and a storyboard↔final comparison), and a "
        "SUPERVOID Pictures screen project from the adaptation dossier (a scene "
        "with two shots, one mapping a graphic-novel storyboard panel), and the "
        "supervised agent framework (a read-only analysis run with findings, a "
        "propose-only run with a gated proposal, and a versioned prompt template), "
        "and the operational integration hub (n8n / ComfyUI / GitHub / Affinity "
        "adapters, with a read-only run, a commit linked to a task, and a "
        "pending-approval webhook event), and the operational business layer "
        "(deepened rights with a window/option/chain-of-title/evidence/status "
        "change, a CRM publisher + reviewer with role/tag/interaction/opportunity, "
        "and an edition with ONIX + press-kit packages), and private curation of "
        "the public reader (cinematic panels on the demo pages with a panel-scoped "
        "hotspot, plus an approved publication request and publication history)."
    )


if __name__ == "__main__":
    run()
