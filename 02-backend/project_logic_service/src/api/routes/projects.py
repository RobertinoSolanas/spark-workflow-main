from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.database import get_db_session
from src.models.schemas.project_schemas import (
    CreateProjectRequest,
    ProjectResponse,
    UpdateProjectRequest,
    UpdateProjectStatusRequest,
)
from src.services.projects import project_service

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    name: str | None = Query(
        None, description="Optional filter string for project name"
    ),
    db: AsyncSession = Depends(get_db_session),
):
    """Retrieve a list of all projects, optionally filtered by name.

    Args:
        name: Optional filter string for project name
        db: SQLAlchemy async session dependency
    Returns:
        list[ProjectResponse]: List of matching project records
    """
    return await project_service.list_projects(
        db=db,
        name=name,
    )


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
)
async def get_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """Retrieve a specific project by its UUID.

    Args:
        project_id: UUID of the project to retrieve
        db: SQLAlchemy async session dependency

    Returns:
        ProjectResponse: The matching project record
    """
    return await project_service.get_project(db=db, project_id=project_id)


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project(
    payload: CreateProjectRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """Create a new project.

    Args:
        payload: Data used to create the project
        db: SQLAlchemy async session dependency

    Returns:
        ProjectResponse: The newly created project record
    """
    project = await project_service.create_project(
        db=db,
        project=payload,
    )

    return project


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
)
async def update_project(
    project_id: UUID,
    payload: UpdateProjectRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """Update fields of an existing project.

    Args:
        project_id: UUID of the project to update
        payload: Fields to update in the project
        db: SQLAlchemy async session dependency

    Returns:
        ProjectResponse: The updated project record
    """
    updated = await project_service.update_project(
        db=db,
        project_id=project_id,
        data=payload,
    )
    return await project_service.get_project(db=db, project_id=updated.id)


@router.patch(
    "/{project_id}/status",
    response_model=ProjectResponse,
)
async def update_project_status(
    project_id: UUID,
    payload: UpdateProjectStatusRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """Update the status of a project.

    Note: This endpoint does NOT handle project transition side effects
    (e.g., queuing jobs). Those should be handled by the main backend service.

    Args:
        project_id: UUID of the project to update
        payload: Request payload containing the target status name
        db: SQLAlchemy async session dependency

    Returns:
        ProjectResponse: The updated project record
    """
    updated = await project_service.update_project_status(
        db=db,
        project_id=project_id,
        payload=payload,
    )
    return await project_service.get_project(db=db, project_id=updated.id)
