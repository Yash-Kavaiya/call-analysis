"""Organization management routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from call_analysis.api.deps import require_admin_user
from call_analysis.database import get_async_session
from call_analysis.models import Organization
from call_analysis.schemas import OrganizationCreate, OrganizationRead, OrganizationUpdate, UserRead

router = APIRouter(prefix="/api/organizations", tags=["Organizations"])


@router.post("", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
async def create_organization(
    body: OrganizationCreate,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[UserRead, Depends(require_admin_user)],
) -> Organization:
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Superuser required")
    existing = await db.execute(select(Organization).where(Organization.slug == body.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Slug already exists")
    org = Organization(name=body.name, slug=body.slug, settings={})
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return org


@router.get("", response_model=list[OrganizationRead])
async def list_organizations(
    db: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[UserRead, Depends(require_admin_user)],
) -> list[Organization]:
    if current_user.is_superuser:
        result = await db.execute(select(Organization).order_by(Organization.created_at.desc()))
        return list(result.scalars().all())
    org = await db.get(Organization, current_user.organization_id)
    return [org] if org else []


@router.get("/{org_id}", response_model=OrganizationRead)
async def get_organization(
    org_id: UUID,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[UserRead, Depends(require_admin_user)],
) -> Organization:
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if not current_user.is_superuser and org.id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return org


@router.patch("/{org_id}", response_model=OrganizationRead)
async def update_organization(
    org_id: UUID,
    body: OrganizationUpdate,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[UserRead, Depends(require_admin_user)],
) -> Organization:
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if not current_user.is_superuser and org.id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if body.name is not None:
        org.name = body.name
    if body.settings is not None:
        org.settings = body.settings
    if body.is_active is not None:
        org.is_active = body.is_active
    await db.commit()
    await db.refresh(org)
    return org
