from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.database import get_db_session
from src.models.schemas.process_step_schemas import ProcessStepResponse
from src.services.process_steps import process_step_service

router = APIRouter(prefix="/process-steps", tags=["ProcessSteps"])


@router.get("", response_model=list[ProcessStepResponse])
async def list_process_steps(
    project_type_id: UUID | None = Query(
        None, description="Optional filter for process steps by project type"
    ),
    db: AsyncSession = Depends(get_db_session),
):
    """Retrieve a list of all ProcessSteps, filtered by project_type_id.

    Args:
        project_type_id: Filter for process steps
        db: SQLAlchemy async session dependency

    Returns:
        list[ProcessStepResponse]: List of matching process step records
    """
    return await process_step_service.list_process_steps(
        db=db,
        project_type_id=project_type_id,
    )


@router.get("/{process_step_id}", response_model=ProcessStepResponse)
async def get_process_step(
    process_step_id: UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """Retrieve a specific process step by its UUID.

    Args:
        process_step_id: UUID of the process step to retrieve
        db: SQLAlchemy async session dependency

    Returns:
        ProcessStepResponse: The matching process step record
    """
    return await process_step_service.get_process_step(
        db=db, process_step_id=process_step_id
    )
