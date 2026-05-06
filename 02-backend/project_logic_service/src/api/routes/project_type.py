from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.database import get_db_session
from src.models.schemas.project_type_schemas import (
    CreateProjectTypeRequest,
    ProjectTypeResponse,
    UpdateProjectTypeRequest,
)
from src.services.project_type import project_type_service

router = APIRouter(
    prefix="/project-types",
    tags=["Project Types"],
)


@router.get("", response_model=list[ProjectTypeResponse])
async def list_project_types(
    db: AsyncSession = Depends(get_db_session),
) -> list[ProjectTypeResponse]:
    """Get a list of all project types.

    Args:
        db: Database session dependency

    Returns:
        List of all project types with id and name
    """
    types = await project_type_service.list_project_types(db=db)
    return [ProjectTypeResponse(id=pt.id, name=pt.name) for pt in types]


@router.post("", response_model=list[ProjectTypeResponse], status_code=status.HTTP_201_CREATED)
async def create_project_types(
    payload: list[CreateProjectTypeRequest],
    db: AsyncSession = Depends(get_db_session),
) -> list[ProjectTypeResponse]:
    """Bulk-create project types.

    Args:
        payload: List of project types to create
        db: Database session dependency

    Returns:
        List of newly created project types
    """
    created = await project_type_service.create_project_types(db=db, items=payload)
    return [ProjectTypeResponse(id=pt.id, name=pt.name) for pt in created]


@router.patch("", response_model=list[ProjectTypeResponse])
async def update_project_types(
    payload: list[UpdateProjectTypeRequest],
    db: AsyncSession = Depends(get_db_session),
) -> list[ProjectTypeResponse]:
    """Bulk-update project types.

    Args:
        payload: List of project types to update (must include id and name)
        db: Database session dependency

    Returns:
        List of updated project types
    """
    updated = await project_type_service.update_project_types(db=db, items=payload)
    return [ProjectTypeResponse(id=pt.id, name=pt.name) for pt in updated]


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_types(
    ids: list[UUID] = Query(..., description="List of project type IDs to delete"),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    """Bulk-delete project types by ID.

    Args:
        ids: List of UUIDs to delete
        db: Database session dependency
    """
    await project_type_service.delete_project_types(db=db, ids=ids)
