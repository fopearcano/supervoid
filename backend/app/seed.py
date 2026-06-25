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
    PublicHotspot,
    PublicMediaAsset,
    PublishedChapter,
    PublishedPage,
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
from app.services import policy
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


def _seed_integration_points(session: Session) -> None:
    points = [
        IntegrationPoint(
            name="LOGOSFORGE — manuscript import",
            type=IntegrationPointType.LOGOSFORGE,
            status=IntegrationPointStatus.PLANNED,
            endpoint="logosforge://export/manuscripts",
            notes=(
                "Bridge to the separate LOGOSFORGE writing subsystem; pull "
                "finished drafts into SUPERVOID Publishing as manuscripts."
            ),
        ),
        IntegrationPoint(
            name="SUPERVOID Movies — adaptation hand-off",
            type=IntegrationPointType.SUPERVOID_MOVIES,
            status=IntegrationPointStatus.PLANNED,
            endpoint="supervoid-movies://adaptations/intake",
            notes=(
                "Future division; hand off works flagged as adaptation "
                "candidates (e.g. The Silent Workshop) for screen development."
            ),
        ),
        IntegrationPoint(
            name="AI Lab — editorial assistance",
            type=IntegrationPointType.AI_LAB,
            status=IntegrationPointStatus.PLANNED,
            endpoint=None,
            notes="Editorial AI features run locally; AI Lab seam reserved.",
        ),
        IntegrationPoint(
            name="Archive / Knowledge Graph",
            type=IntegrationPointType.ARCHIVE_KNOWLEDGE_GRAPH,
            status=IntegrationPointStatus.ACTIVE,
            endpoint="/api/knowledge",
            notes="Editorial knowledge graph available in-app.",
        ),
    ]
    session.add_all(points)
    session.commit()


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
        _seed_integration_points(session)
        _seed_knowledge_graph(session, manuscripts)
        _seed_public_reader(session, works)
        _seed_transmedia(session, works, authors)
        _seed_collaboration(session, users, works)
        _seed_production_tasks(session, works, users)
        _seed_asset_library(session, works, authors, users)

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
        "licence, plus a human-made character design)."
    )


if __name__ == "__main__":
    run()
