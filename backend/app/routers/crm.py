"""Relationship memory — the private studio CRM API.

Organizations, contacts (with roles and tags), manually-logged interactions and
a light opportunity pipeline. This API only *records* relationships: there is no
endpoint that sends communication or imports contacts from external sources.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from app.auth import ADMIN_ONLY, AUTHED, get_current_user
from app.db import get_session
from app.models import (
    Contact,
    ContactRole,
    ContactTag,
    ContactTagLink,
    Interaction,
    Opportunity,
    Organization,
    User,
)
from app.models.enums import (
    ContactRoleKind,
    OpportunityStatus,
    OrganizationKind,
)
from app.schemas import (
    ContactCreate,
    ContactDetail,
    ContactRead,
    ContactRoleCreate,
    ContactRoleRead,
    ContactTagCreate,
    ContactTagRead,
    ContactUpdate,
    InteractionCreate,
    InteractionRead,
    InteractionUpdate,
    OpportunityCreate,
    OpportunityRead,
    OpportunityUpdate,
    OrganizationCreate,
    OrganizationRead,
    OrganizationUpdate,
    TagAssignRequest,
)
from app.services.knowledge import slugify
from app.utils import (
    Page,
    PageParams,
    apply_patch,
    ensure_exists,
    get_or_404,
    page_params,
    paginate,
)

router = APIRouter(tags=["crm"])


# --- organizations ---------------------------------------------------------


@router.get("/organizations", response_model=Page[OrganizationRead])
def list_organizations(
    session: Session = Depends(get_session),
    params: PageParams = Depends(page_params),
    kind: Optional[OrganizationKind] = Query(default=None),
    q: Optional[str] = Query(default=None, description="Name search"),
) -> Page[OrganizationRead]:
    stmt = select(Organization)
    if kind is not None:
        stmt = stmt.where(Organization.kind == kind)
    if q:
        stmt = stmt.where(Organization.name.ilike(f"%{q}%"))
    stmt = stmt.order_by(Organization.name)
    items, total = paginate(session, stmt, params)
    return Page[OrganizationRead](
        items=[OrganizationRead.model_validate(o) for o in items],
        total=total, skip=params.skip, limit=params.limit,
    )


@router.get("/organizations/{org_id}", response_model=OrganizationRead)
def get_organization(org_id: str, session: Session = Depends(get_session)) -> Organization:
    return get_or_404(session, Organization, org_id, name="Organization")


@router.post(
    "/organizations", response_model=OrganizationRead,
    status_code=status.HTTP_201_CREATED, dependencies=AUTHED,
)
def create_organization(
    payload: OrganizationCreate, session: Session = Depends(get_session)
) -> Organization:
    org = Organization(**payload.model_dump())
    session.add(org)
    session.commit()
    session.refresh(org)
    return org


@router.patch("/organizations/{org_id}", response_model=OrganizationRead, dependencies=AUTHED)
def update_organization(
    org_id: str, payload: OrganizationUpdate, session: Session = Depends(get_session)
) -> Organization:
    org = get_or_404(session, Organization, org_id, name="Organization")
    apply_patch(org, payload)
    session.add(org)
    session.commit()
    session.refresh(org)
    return org


@router.delete(
    "/organizations/{org_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=ADMIN_ONLY
)
def delete_organization(org_id: str, session: Session = Depends(get_session)):
    org = get_or_404(session, Organization, org_id, name="Organization")
    session.delete(org)
    session.commit()


# --- contact tags ----------------------------------------------------------


@router.get("/contact-tags", response_model=list[ContactTagRead])
def list_contact_tags(session: Session = Depends(get_session)) -> list[ContactTagRead]:
    rows = session.exec(select(ContactTag).order_by(ContactTag.name)).all()
    return [ContactTagRead.model_validate(t) for t in rows]


@router.post(
    "/contact-tags", response_model=ContactTagRead,
    status_code=status.HTTP_201_CREATED, dependencies=AUTHED,
)
def create_contact_tag(
    payload: ContactTagCreate, session: Session = Depends(get_session)
) -> ContactTag:
    slug = slugify(payload.name)
    existing = session.exec(select(ContactTag).where(ContactTag.slug == slug)).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="A tag with this name already exists.")
    tag = ContactTag(
        name=payload.name, slug=slug, color=payload.color, description=payload.description
    )
    session.add(tag)
    session.commit()
    session.refresh(tag)
    return tag


@router.delete(
    "/contact-tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=ADMIN_ONLY
)
def delete_contact_tag(tag_id: str, session: Session = Depends(get_session)):
    tag = get_or_404(session, ContactTag, tag_id, name="ContactTag")
    session.delete(tag)
    session.commit()


# --- contacts --------------------------------------------------------------


def _contact_detail(contact: Contact) -> ContactDetail:
    detail = ContactDetail.model_validate(contact)
    detail.organization = (
        OrganizationRead.model_validate(contact.organization)
        if contact.organization is not None else None
    )
    detail.roles = [ContactRoleRead.model_validate(r) for r in contact.roles]
    detail.tags = [ContactTagRead.model_validate(link.tag) for link in contact.tag_links]
    return detail


@router.get("/contacts", response_model=Page[ContactRead])
def list_contacts(
    session: Session = Depends(get_session),
    params: PageParams = Depends(page_params),
    organization_id: Optional[str] = Query(default=None),
    role: Optional[ContactRoleKind] = Query(default=None),
    tag_id: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None, description="Name search"),
) -> Page[ContactRead]:
    stmt = select(Contact)
    if organization_id is not None:
        stmt = stmt.where(Contact.organization_id == organization_id)
    if role is not None:
        stmt = stmt.where(
            Contact.id.in_(select(ContactRole.contact_id).where(ContactRole.role == role))
        )
    if tag_id is not None:
        stmt = stmt.where(
            Contact.id.in_(
                select(ContactTagLink.contact_id).where(ContactTagLink.tag_id == tag_id)
            )
        )
    if q:
        stmt = stmt.where(Contact.full_name.ilike(f"%{q}%"))
    stmt = stmt.order_by(Contact.full_name)
    items, total = paginate(session, stmt, params)
    return Page[ContactRead](
        items=[ContactRead.model_validate(c) for c in items],
        total=total, skip=params.skip, limit=params.limit,
    )


@router.get("/contacts/{contact_id}", response_model=ContactDetail)
def get_contact(contact_id: str, session: Session = Depends(get_session)) -> ContactDetail:
    contact = get_or_404(session, Contact, contact_id, name="Contact")
    return _contact_detail(contact)


@router.post(
    "/contacts", response_model=ContactDetail,
    status_code=status.HTTP_201_CREATED, dependencies=AUTHED,
)
def create_contact(
    payload: ContactCreate, session: Session = Depends(get_session)
) -> ContactDetail:
    if payload.organization_id is not None:
        ensure_exists(session, Organization, payload.organization_id, name="Organization")
    contact = Contact(**payload.model_dump())
    session.add(contact)
    session.commit()
    session.refresh(contact)
    return _contact_detail(contact)


@router.patch("/contacts/{contact_id}", response_model=ContactDetail, dependencies=AUTHED)
def update_contact(
    contact_id: str, payload: ContactUpdate, session: Session = Depends(get_session)
) -> ContactDetail:
    contact = get_or_404(session, Contact, contact_id, name="Contact")
    apply_patch(contact, payload)
    session.add(contact)
    session.commit()
    session.refresh(contact)
    return _contact_detail(contact)


@router.delete(
    "/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=ADMIN_ONLY
)
def delete_contact(contact_id: str, session: Session = Depends(get_session)):
    contact = get_or_404(session, Contact, contact_id, name="Contact")
    session.delete(contact)
    session.commit()


# --- contact roles & tags --------------------------------------------------


@router.post(
    "/contacts/{contact_id}/roles", response_model=ContactRoleRead,
    status_code=status.HTTP_201_CREATED, dependencies=AUTHED,
)
def add_contact_role(
    contact_id: str, payload: ContactRoleCreate, session: Session = Depends(get_session)
) -> ContactRole:
    ensure_exists(session, Contact, contact_id, name="Contact")
    if payload.organization_id is not None:
        ensure_exists(session, Organization, payload.organization_id, name="Organization")
    role = ContactRole(contact_id=contact_id, **payload.model_dump())
    session.add(role)
    session.commit()
    session.refresh(role)
    return role


@router.delete(
    "/contacts/{contact_id}/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT,
    dependencies=AUTHED,
)
def remove_contact_role(
    contact_id: str, role_id: str, session: Session = Depends(get_session)
):
    role = get_or_404(session, ContactRole, role_id, name="ContactRole")
    session.delete(role)
    session.commit()


@router.post(
    "/contacts/{contact_id}/tags", response_model=ContactDetail, dependencies=AUTHED
)
def assign_tag(
    contact_id: str, payload: TagAssignRequest, session: Session = Depends(get_session)
) -> ContactDetail:
    contact = get_or_404(session, Contact, contact_id, name="Contact")
    ensure_exists(session, ContactTag, payload.tag_id, name="ContactTag")
    existing = session.exec(
        select(ContactTagLink).where(
            ContactTagLink.contact_id == contact_id,
            ContactTagLink.tag_id == payload.tag_id,
        )
    ).first()
    if existing is None:
        session.add(ContactTagLink(contact_id=contact_id, tag_id=payload.tag_id))
        session.commit()
        session.refresh(contact)
    return _contact_detail(contact)


@router.delete(
    "/contacts/{contact_id}/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT,
    dependencies=AUTHED,
)
def unassign_tag(
    contact_id: str, tag_id: str, session: Session = Depends(get_session)
):
    link = session.exec(
        select(ContactTagLink).where(
            ContactTagLink.contact_id == contact_id, ContactTagLink.tag_id == tag_id
        )
    ).first()
    if link is not None:
        session.delete(link)
        session.commit()


# --- interactions (manual log only — never auto-sent) ----------------------


@router.get("/interactions", response_model=Page[InteractionRead])
def list_interactions(
    session: Session = Depends(get_session),
    params: PageParams = Depends(page_params),
    contact_id: Optional[str] = Query(default=None),
    organization_id: Optional[str] = Query(default=None),
    work_id: Optional[str] = Query(default=None),
) -> Page[InteractionRead]:
    stmt = select(Interaction)
    if contact_id is not None:
        stmt = stmt.where(Interaction.contact_id == contact_id)
    if organization_id is not None:
        stmt = stmt.where(Interaction.organization_id == organization_id)
    if work_id is not None:
        stmt = stmt.where(Interaction.work_id == work_id)
    stmt = stmt.order_by(Interaction.occurred_at.desc())
    items, total = paginate(session, stmt, params)
    return Page[InteractionRead](
        items=[InteractionRead.model_validate(i) for i in items],
        total=total, skip=params.skip, limit=params.limit,
    )


@router.post(
    "/interactions", response_model=InteractionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_interaction(
    payload: InteractionCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Interaction:
    if payload.contact_id is not None:
        ensure_exists(session, Contact, payload.contact_id, name="Contact")
    if payload.organization_id is not None:
        ensure_exists(session, Organization, payload.organization_id, name="Organization")
    data = payload.model_dump(exclude_none=True)
    interaction = Interaction(**data, created_by_id=user.id)
    session.add(interaction)
    session.commit()
    session.refresh(interaction)
    return interaction


@router.patch("/interactions/{interaction_id}", response_model=InteractionRead, dependencies=AUTHED)
def update_interaction(
    interaction_id: str, payload: InteractionUpdate, session: Session = Depends(get_session)
) -> Interaction:
    interaction = get_or_404(session, Interaction, interaction_id, name="Interaction")
    apply_patch(interaction, payload)
    session.add(interaction)
    session.commit()
    session.refresh(interaction)
    return interaction


@router.delete(
    "/interactions/{interaction_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=AUTHED
)
def delete_interaction(interaction_id: str, session: Session = Depends(get_session)):
    interaction = get_or_404(session, Interaction, interaction_id, name="Interaction")
    session.delete(interaction)
    session.commit()


# --- opportunities ---------------------------------------------------------


@router.get("/opportunities", response_model=Page[OpportunityRead])
def list_opportunities(
    session: Session = Depends(get_session),
    params: PageParams = Depends(page_params),
    status_: Optional[OpportunityStatus] = Query(default=None, alias="status"),
    contact_id: Optional[str] = Query(default=None),
    organization_id: Optional[str] = Query(default=None),
    work_id: Optional[str] = Query(default=None),
) -> Page[OpportunityRead]:
    stmt = select(Opportunity)
    if status_ is not None:
        stmt = stmt.where(Opportunity.status == status_)
    if contact_id is not None:
        stmt = stmt.where(Opportunity.contact_id == contact_id)
    if organization_id is not None:
        stmt = stmt.where(Opportunity.organization_id == organization_id)
    if work_id is not None:
        stmt = stmt.where(Opportunity.work_id == work_id)
    stmt = stmt.order_by(Opportunity.created_at.desc())
    items, total = paginate(session, stmt, params)
    return Page[OpportunityRead](
        items=[OpportunityRead.model_validate(o) for o in items],
        total=total, skip=params.skip, limit=params.limit,
    )


@router.get("/opportunities/{opportunity_id}", response_model=OpportunityRead)
def get_opportunity(opportunity_id: str, session: Session = Depends(get_session)) -> Opportunity:
    return get_or_404(session, Opportunity, opportunity_id, name="Opportunity")


@router.post(
    "/opportunities", response_model=OpportunityRead,
    status_code=status.HTTP_201_CREATED,
)
def create_opportunity(
    payload: OpportunityCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Opportunity:
    opp = Opportunity(**payload.model_dump(), owner_id=user.id)
    session.add(opp)
    session.commit()
    session.refresh(opp)
    return opp


@router.patch("/opportunities/{opportunity_id}", response_model=OpportunityRead, dependencies=AUTHED)
def update_opportunity(
    opportunity_id: str, payload: OpportunityUpdate, session: Session = Depends(get_session)
) -> Opportunity:
    opp = get_or_404(session, Opportunity, opportunity_id, name="Opportunity")
    apply_patch(opp, payload)
    session.add(opp)
    session.commit()
    session.refresh(opp)
    return opp


@router.delete(
    "/opportunities/{opportunity_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=ADMIN_ONLY
)
def delete_opportunity(opportunity_id: str, session: Session = Depends(get_session)):
    opp = get_or_404(session, Opportunity, opportunity_id, name="Opportunity")
    session.delete(opp)
    session.commit()
