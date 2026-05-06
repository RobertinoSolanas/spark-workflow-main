from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.database import get_db_session
from src.models.schemas.deadline_schemas import (
    CreateDeadlineRequest,
    DeadlineResponse,
    UpdateDeadlineRequest,
)
from src.services.deadlines import deadline_service

router = APIRouter(prefix="/deadlines", tags=["Deadlines"])


@router.get("", response_model=list[DeadlineResponse])
async def list_deadlines(
    project_id: UUID | None = Query(
        None, description="Optional project ID to filter deadlines by"
    ),
    db: AsyncSession = Depends(get_db_session),
):
    """List deadlines, optionally filtered by project.

    Args:
        project_id: Optional project ID to filter by
        db: SQLAlchemy async database session

    Returns:
        list[DeadlineResponse]: Deadlines ordered by end date
    """
    return await deadline_service.list_deadlines(
        db=db,
        project_id=project_id,
    )


@router.post(
    "",
    response_model=DeadlineResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_deadline(
    payload: CreateDeadlineRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """Create a new deadline for a project.

    Args:
        payload: Deadline data including project ID
        db: SQLAlchemy async database session

    Returns:
        DeadlineResponse: The created deadline
    """
    return await deadline_service.create_deadline(
        db=db,
        deadline_data=payload,
    )


@router.patch("/{deadline_id}", response_model=DeadlineResponse)
async def update_deadline(
    deadline_id: UUID,
    payload: UpdateDeadlineRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """Update an existing deadline.

    Args:
        deadline_id: UUID of the deadline to update
        payload: Updated deadline data
        db: SQLAlchemy async database session

    Returns:
        DeadlineResponse: The updated deadline
    """
    return await deadline_service.update_deadline(
        db=db,
        deadline_id=deadline_id,
        deadline_data=payload,
    )


@router.delete("/{deadline_id}", response_model=DeadlineResponse)
async def delete_deadline(
    deadline_id: UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """Delete a deadline.

    Args:
        deadline_id: UUID of the deadline to delete
        db: SQLAlchemy async database session

    Returns:
        DeadlineResponse: The deleted deadline
    """
    return await deadline_service.delete_deadline(
        db=db,
        deadline_id=deadline_id,
    )


@router.get("/{deadline_id}", response_model=DeadlineResponse)
async def get_deadline(
    deadline_id: UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """Retrieve a single deadline by ID.

    Args:
        deadline_id: UUID of the deadline to retrieve
        db: SQLAlchemy async database session

    Returns:
        DeadlineResponse: The requested deadline
    """
    return await deadline_service.get_deadline(
        db=db,
        deadline_id=deadline_id,
    )
