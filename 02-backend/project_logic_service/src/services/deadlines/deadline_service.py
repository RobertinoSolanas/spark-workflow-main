from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.exceptions import DeadlineNotFoundError
from src.models.db_models import Deadline
from src.models.schemas.deadline_schemas import (
    CreateDeadlineRequest,
    UpdateDeadlineRequest,
)


async def create_deadline(
    db: AsyncSession,
    deadline_data: CreateDeadlineRequest,
) -> Deadline:
    """Create a new deadline for a given project.

    Args:
        db: Async SQLAlchemy session
        deadline_data: Deadline creation data including project ID

    Returns:
        The created deadline instance
    """
    deadline = Deadline(
        project_id=deadline_data.project_id,
        start_at=deadline_data.start_at,
        end_at=deadline_data.end_at,
        deadline_type=deadline_data.deadline_type,
        legal_basis=deadline_data.legal_basis,
    )

    db.add(deadline)
    await db.commit()
    await db.refresh(deadline)
    return deadline


async def get_deadline(db: AsyncSession, deadline_id: UUID) -> Deadline:
    """Retrieve a deadline by its unique identifier.

    Args:
        db: Async SQLAlchemy session
        deadline_id: UUID of the deadline to retrieve

    Returns:
        The deadline if found

    Raises:
        DeadlineNotFoundError: If deadline is not found
    """
    result = await db.execute(select(Deadline).where(Deadline.id == deadline_id))
    deadline = result.scalars().first()
    if not deadline:
        raise DeadlineNotFoundError(str(deadline_id))
    return deadline


async def list_deadlines(
    db: AsyncSession,
    project_id: UUID | None = None,
) -> Sequence[Deadline]:
    """List deadlines, optionally filtered by project.

    Args:
        db: Async SQLAlchemy session
        project_id: If provided, return only deadlines for this project

    Returns:
        List of deadline instances, ordered by end date
    """
    query = select(Deadline)
    if project_id is not None:
        query = query.where(Deadline.project_id == project_id)
    query = query.order_by(Deadline.end_at.asc())
    result = await db.execute(query)
    return result.scalars().all()


async def update_deadline(
    db: AsyncSession,
    deadline_id: UUID,
    deadline_data: UpdateDeadlineRequest,
) -> Deadline:
    """Update an existing deadline.

    Args:
        db: Async SQLAlchemy session
        deadline_id: UUID of the deadline to update
        deadline_data: Data to update the deadline with

    Returns:
        The updated deadline

    Raises:
        DeadlineNotFoundError: If deadline not found
    """
    deadline = await get_deadline(db=db, deadline_id=deadline_id)

    update_data = deadline_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(deadline, key, value)

    await db.commit()
    await db.refresh(deadline)
    return deadline


async def delete_deadline(
    db: AsyncSession,
    deadline_id: UUID,
) -> Deadline:
    """Delete a deadline.

    Args:
        db: Async SQLAlchemy session
        deadline_id: UUID of the deadline to delete

    Returns:
        The deleted deadline instance

    Raises:
        DeadlineNotFoundError: If deadline not found
    """
    deadline = await get_deadline(db=db, deadline_id=deadline_id)

    await db.delete(deadline)
    await db.commit()
    return deadline
