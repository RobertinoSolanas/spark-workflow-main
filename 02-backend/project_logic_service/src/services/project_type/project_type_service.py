from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.exceptions import (
    DuplicateProjectTypeError,
    ForeignKeyViolationError,
    IntegrityError,
    ProjectTypeNotFoundError,
    RequestValidationError,
)
from src.models.db_models import ProjectType
from src.models.schemas.project_type_schemas import (
    CreateProjectTypeRequest,
    UpdateProjectTypeRequest,
)


async def list_project_types(db: AsyncSession) -> Sequence[ProjectType]:
    """Retrieve all project types.

    Args:
        db: Async SQLAlchemy session

    Returns:
        List of all ProjectType records
    """
    result = await db.execute(select(ProjectType))
    return result.scalars().all()


async def create_project_types(
    db: AsyncSession,
    items: list[CreateProjectTypeRequest],
) -> Sequence[ProjectType]:
    """Bulk-create project types.

    Args:
        db: Async SQLAlchemy session
        items: List of project type creation payloads

    Returns:
        List of newly created ProjectType records
    """
    new_types = [ProjectType(name=item.name) for item in items]
    db.add_all(new_types)
    try:
        await db.flush()
        for pt in new_types:
            await db.refresh(pt)
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise DuplicateProjectTypeError("") from e
    return new_types


async def update_project_types(
    db: AsyncSession,
    items: list[UpdateProjectTypeRequest],
) -> Sequence[ProjectType]:
    """Bulk-update project types by id.

    Args:
        db: Async SQLAlchemy session
        items: List of project type update payloads (id + name)

    Returns:
        List of updated ProjectType records
    """
    if not items:
        return []

    incoming_ids = [item.id for item in items]
    if len(incoming_ids) != len(set(incoming_ids)):
        raise RequestValidationError([])

    async with db.begin():
        result = await db.execute(
            select(ProjectType).where(ProjectType.id.in_(incoming_ids))
        )
        records = {pt.id: pt for pt in result.scalars().all()}

        for item in items:
            if item.id in records:
                records[item.id].name = item.name

    for pt in records.values():
        await db.refresh(pt)
    return list(records.values())


async def delete_project_types(db: AsyncSession, ids: list[UUID]) -> None:
    """Bulk-delete project types by id.

    Args:
        db: Async SQLAlchemy session
        ids: List of UUIDs to delete

    Raises:
        ProjectTypeNotFoundError: If any id is not found
    """
    if len(ids) != len(set(ids)):
        raise RequestValidationError([])

    records = []
    for id_ in ids:
        result = await db.execute(select(ProjectType).where(ProjectType.id == id_))
        pt = result.scalar_one_or_none()
        if pt is None:
            raise ProjectTypeNotFoundError(str(id_))
        records.append(pt)
    try:
        for pt in records:
            await db.delete(pt)
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        if isinstance(e.orig, ForeignKeyViolationError):
            raise e.orig from e
        raise
