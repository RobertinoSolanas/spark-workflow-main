from collections.abc import Sequence
from typing import TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db_models import Base

ModelType = TypeVar("ModelType", bound=Base)


async def list_types[ModelType](
    db: AsyncSession, model: ModelType
) -> Sequence[ModelType]:
    """Generic function to retrieve all rows of a type table with id and name.

    Args:
        db: Async SQLAlchemy session
        model: SQLAlchemy model class

    Returns:
        List of records with id and name
    """
    result = await db.execute(select(model))
    return result.scalars().all()


async def get_type[ModelType](
    db: AsyncSession,
    model: ModelType,
    record_id: UUID,
) -> ModelType | None:
    """Retrieve a single record from a type table by its UUID.

    Args:
        db: Async SQLAlchemy async session
        model: SQLAlchemy model class to query
        record_id: Primary key of the record to retrieve

    Returns:
        Type record if found, otherwise None
    """
    result = await db.execute(select(model).where(model.id == record_id))
    return result.scalar_one_or_none()
