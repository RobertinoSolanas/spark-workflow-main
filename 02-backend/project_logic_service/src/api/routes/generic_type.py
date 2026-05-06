from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.database import get_db_session
from src.models.db_models import ProjectStatus
from src.models.schemas.generic_type_schemas import TypeResponse
from src.services.generic_type import generic_type_service

router = APIRouter(prefix="", tags=["Types/Statuses"])


@router.get("/project-statuses", response_model=list[TypeResponse])
async def list_project_statuses(
    db: AsyncSession = Depends(get_db_session),
) -> list[TypeResponse]:
    """Get a list of all project statuses.

    Args:
        db: Database session dependency

    Returns:
        List of all project statuses with id and name
    """
    types = await generic_type_service.list_types(db=db, model=ProjectStatus)
    return [TypeResponse(id=str(t.id), name=t.name) for t in types]
