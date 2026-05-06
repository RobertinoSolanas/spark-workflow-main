"""API routes for template category and document type CRUD operations."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.database import get_db_session
from src.models.schemas.template_management_schemas import (
    MAX_TEMPLATE_CATEGORIES_PER_REQUEST,
    CreateTemplateCategoryRequest,
    TemplateCategoryResponse,
    TemplateSoftDeleteResponse,
)
from src.services.template_management_service import (
    create_template_categories,
    get_template_categories,
    soft_delete_all_templates,
)

router = APIRouter(
    prefix="/{project_type_id}/template-categories",
    tags=["Template Management"],
)


@router.get(
    "",
    response_model=list[TemplateCategoryResponse],
)
async def list_template_categories(
    project_type_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> list[TemplateCategoryResponse]:
    """List all non-deleted template categories with their document types."""
    return await get_template_categories(project_type_id, db)


@router.post(
    "",
    response_model=list[TemplateCategoryResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_categories(
    project_type_id: UUID,
    payload: Annotated[
        list[CreateTemplateCategoryRequest],
        Body(max_length=MAX_TEMPLATE_CATEGORIES_PER_REQUEST),
    ],
    db: AsyncSession = Depends(get_db_session),
) -> list[TemplateCategoryResponse]:
    """Create template categories with nested document types."""
    return await create_template_categories(project_type_id, payload, db)


@router.delete(
    "",
    response_model=TemplateSoftDeleteResponse,
)
async def delete_all_template_data(
    project_type_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> TemplateSoftDeleteResponse:
    """Soft-delete all template categories and document types for a project type."""
    return await soft_delete_all_templates(project_type_id, db)
