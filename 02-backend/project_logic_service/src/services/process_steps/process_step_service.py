from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db_models import ProcessStep, ProjectType


async def list_process_steps(
    db: AsyncSession, project_type_id: UUID | None = None
) -> Sequence[ProcessStep]:
    """Retrieve a list of all process steps, filtered by project_type_id.

    Args:
        db: Async database session
        project_type_id: Filter UUID for project types

    Returns:
        List of matching ProcessStep instances
    """
    query = select(ProcessStep)
    if project_type_id:
        query = query.where(ProcessStep.project_type_id == project_type_id)

    result = await db.execute(query)
    return result.scalars().all()


async def get_process_step(
    db: AsyncSession,
    process_step_id: UUID,
) -> ProcessStep:
    """Retrieve a single process step by its unique ID.

    Args:
        db: Async database session
        process_step_id: Unique identifier of the process step

    Returns:
        The ProcessStep instance if found

    Raises:
        ProcessStepNotFoundError: If process step is not found
    """
    result = await db.execute(
        select(ProcessStep).where(ProcessStep.id == process_step_id)
    )
    process_step = result.scalar_one_or_none()
    if not process_step:
        from src.exceptions import ProcessStepNotFoundError

        raise ProcessStepNotFoundError(str(process_step_id))
    return process_step


async def get_process_step_id(
    db: AsyncSession,
    process_step_index: int,
    project_type: str,
) -> UUID | None:
    """Retrieve the ID of a process step for a given project type and step index.

    Args:
        db: SQLAlchemy asynchronous session used for database access
        process_step_index: The index (order) of the process step within the project type
        project_type: The name of the project type to filter by

    Returns:
        The UUID of the matching process step if found, otherwise None
    """
    stmt = (
        select(ProcessStep.id)
        .join(ProjectType, ProcessStep.project_type_id == ProjectType.id)
        .where(ProjectType.name == project_type)
        .where(ProcessStep.process_step_index == process_step_index)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
