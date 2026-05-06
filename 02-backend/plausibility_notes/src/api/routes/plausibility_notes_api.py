"""API routes for plausibility note management."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.database import get_db_session
from src.models.schemas.plausibility_notes import (
    JobDoneRequest,
    JobDoneResponse,
    PlausibilityCheckResult,
    SuccessResponse,
    UpdateNoteRequest,
)
from src.services.plausibility_notes_service import (
    delete_note,
    get_plausibility_notes,
    process_job_results,
    update_note_status,
)

router = APIRouter(prefix="/plausibility-notes", tags=["Plausibility Notes"])


@router.get(
    "/{project_id}",
    response_model=PlausibilityCheckResult,
)
async def get_notes(
    project_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> PlausibilityCheckResult:
    """Return all plausibility notes for the specified project."""
    return await get_plausibility_notes(project_id, db)


@router.post(
    "/{project_id}/job-done",
    response_model=JobDoneResponse,
    status_code=status.HTTP_200_OK,
)
async def job_done(
    project_id: UUID,
    payload: JobDoneRequest,
    db: AsyncSession = Depends(get_db_session),
) -> JobDoneResponse:
    """Process completed plausibility check job results.

    Fetches the results JSON from Document Management Service using the provided
    file_id, clears existing data for the project, and stores the new results.
    """
    return await process_job_results(project_id, payload.file_id, db)


@router.patch(
    "/notes/{note_id}",
    response_model=SuccessResponse,
)
async def update_note(
    note_id: UUID,
    payload: UpdateNoteRequest,
    db: AsyncSession = Depends(get_db_session),
) -> SuccessResponse:
    """Update the status of a plausibility note."""
    note = await update_note_status(note_id, payload.status, db)
    if note is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Note not found"
        )
    return SuccessResponse()


@router.delete(
    "/notes/{note_id}",
    response_model=SuccessResponse,
)
async def delete_single_note(
    note_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> SuccessResponse:
    """Delete a plausibility note by ID."""
    deleted = await delete_note(note_id, db)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Note not found"
        )
    return SuccessResponse()
