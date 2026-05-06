"""Business logic for plausibility note management."""

from uuid import UUID

import httpx
from event_logging.enums import (
    EventAction,
    EventCategory,
    EventOutcome,
    LogEventDefault,
)
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from tenacity import retry, retry_if_exception_type, stop_after_attempt

from src.config.settings import settings
from src.models.db_models import PlausibilityNote, PlausibilityNoteOccurrence
from src.models.schemas.plausibility_notes import (
    Contradiction,
    ContradictionOccurrence,
    FileDownloadResponse,
    JobDoneResponse,
    PlausibilityCheckResult,
    PlausibilityNoteStatus,
)
from src.utils.logger import logger


@retry(
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException)),
)
async def _fetch_download_url(
    download_url_endpoint: str,
) -> FileDownloadResponse:
    """Fetch presigned download URL for a file from Document Management Service."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(download_url_endpoint)
        response.raise_for_status()
        return FileDownloadResponse.model_validate(response.json())


@retry(
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException)),
)
async def _fetch_json_content(
    download_url: str,
) -> PlausibilityCheckResult:
    """Fetch and parse JSON content from presigned URL."""
    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        headers={
            "Content-Type": "application/json",
        },
    ) as gcs_client:
        response = await gcs_client.get(download_url)
        response.raise_for_status()
        return PlausibilityCheckResult.model_validate_json(response.content)


async def fetch_results_file(file_id: UUID) -> PlausibilityCheckResult:
    """Fetch and parse the results JSON from Document Management Service."""
    base_url = settings.DOCUMENT_MANAGEMENT_SERVICE_URL.rstrip("/")
    download_url_endpoint = f"{base_url}/v2/files/{file_id}/generate-download-url"

    logger.debug(
        EventAction.READ,
        EventOutcome.UNKNOWN,
        EventCategory.API,
        default_event=LogEventDefault.EXTERNAL_SERVICE_INTERACTION,
        message=f"Fetching download URL from {download_url_endpoint}",
    )

    download_info = await _fetch_download_url(download_url_endpoint)
    logger.debug(
        EventAction.READ,
        EventOutcome.SUCCESS,
        EventCategory.API,
        default_event=LogEventDefault.EXTERNAL_SERVICE_INTERACTION,
        message=f"Obtained presigned download URL for file_id={file_id}",
    )

    return await _fetch_json_content(download_info.download_url)


async def delete_all_for_project(project_id: UUID, db: AsyncSession) -> int:
    """Delete all plausibility notes for a project."""
    logger.info(
        EventAction.DELETE,
        EventOutcome.UNKNOWN,
        EventCategory.DATABASE,
        default_event=LogEventDefault.DB_WRITE,
        message=f"Deleting all plausibility notes for project_id={project_id}",
    )

    # Cascading delete should handle occurrences
    result = await db.execute(
        delete(PlausibilityNote).where(PlausibilityNote.project_id == project_id)
    )
    deleted_count = result.rowcount

    logger.info(
        EventAction.DELETE,
        EventOutcome.UNKNOWN,
        EventCategory.DATABASE,
        default_event=LogEventDefault.DB_WRITE,
        message=f"Deleted {deleted_count} plausibility notes for project_id={project_id} (pending commit)",
    )
    return deleted_count


async def bulk_insert_results(
    project_id: UUID,
    results: PlausibilityCheckResult,
    db: AsyncSession,
) -> None:
    """Insert plausibility notes and occurrences from job results."""
    notes_count = 0
    for contradiction in results.contradictions:
        note = PlausibilityNote(
            id=contradiction.id,
            project_id=project_id,
            description=contradiction.description,
            status=contradiction.status.value,
        )
        db.add(note)
        notes_count += 1

        for occ in contradiction.occurrences:
            occurrence = PlausibilityNoteOccurrence(
                plausibility_note_id=note.id,
                document_id=occ.document_id,
                document_name=occ.document_name,
                content_excerpt=occ.content_excerpt,
                page_number=occ.page_number,
            )
            db.add(occurrence)

    await db.flush()

    logger.info(
        EventAction.WRITE,
        EventOutcome.SUCCESS,
        EventCategory.DATABASE,
        default_event=LogEventDefault.DB_WRITE,
        message=f"Inserted {notes_count} plausibility notes for project {project_id}",
    )


async def process_job_results(
    project_id: UUID,
    file_id: UUID,
    db: AsyncSession,
) -> JobDoneResponse:
    """Process job results: fetch, delete old data, insert new data."""
    logger.info(
        EventAction.WRITE,
        EventOutcome.UNKNOWN,
        EventCategory.DATABASE,
        default_event=LogEventDefault.GENERAL,
        message=f"Processing job results for project_id={project_id}, file_id={file_id}",
    )

    logger.info(
        EventAction.READ,
        EventOutcome.UNKNOWN,
        EventCategory.API,
        default_event=LogEventDefault.EXTERNAL_SERVICE_INTERACTION,
        message="Fetching results file from document management service",
    )
    results = await fetch_results_file(file_id)

    if not results.contradictions:
        logger.warn(
            EventAction.VALIDATE,
            EventOutcome.UNKNOWN,
            EventCategory.DATABASE,
            default_event=LogEventDefault.VALIDATION_FAILURE,
            message=f"Results contain no contradictions for project_id={project_id}",
        )

    contradictions_count = len(results.contradictions)
    total_occurrences = sum(
        len(c.occurrences) for c in results.contradictions
    )

    try:
        logger.info(
            EventAction.DELETE,
            EventOutcome.UNKNOWN,
            EventCategory.DATABASE,
            default_event=LogEventDefault.DB_WRITE,
            message=f"Deleting existing plausibility notes for project_id={project_id}",
        )
        deleted_count = await delete_all_for_project(project_id, db)

        logger.info(
            EventAction.WRITE,
            EventOutcome.UNKNOWN,
            EventCategory.DATABASE,
            default_event=LogEventDefault.DB_WRITE,
            message=f"Inserting new plausibility notes for project_id={project_id}",
        )
        await bulk_insert_results(project_id, results, db)

        await db.commit()
        logger.info(
            EventAction.WRITE,
            EventOutcome.SUCCESS,
            EventCategory.DATABASE,
            default_event=LogEventDefault.DB_COMMIT,
            message=f"Successfully processed job results for project_id={project_id}",
        )

        return JobDoneResponse(
            status="no_contradictions" if not contradictions_count else "contradictions_found",
            contradictions_found=contradictions_count,
            total_occurrences=total_occurrences,
            previous_records_deleted=deleted_count,
        )

    except Exception as e:
        logger.error(
            EventAction.WRITE,
            EventOutcome.FAILURE,
            EventCategory.DATABASE,
            default_event=LogEventDefault.DB_ERROR,
            message=f"Failed to process job results for project_id={project_id}: {e!s}",
        )
        await db.rollback()
        raise


async def update_note_status(
    note_id: UUID,
    status: PlausibilityNoteStatus,
    db: AsyncSession,
) -> PlausibilityNote | None:
    """Update the status of a plausibility note."""
    result = await db.execute(
        select(PlausibilityNote).where(PlausibilityNote.id == note_id)
    )
    note = result.scalar_one_or_none()
    if note is None:
        return None
    note.status = status.value
    await db.commit()
    return note


async def delete_note(
    note_id: UUID,
    db: AsyncSession,
) -> bool:
    """Delete a single plausibility note by ID."""
    result = await db.execute(
        delete(PlausibilityNote).where(PlausibilityNote.id == note_id)
    )
    await db.commit()
    return result.rowcount > 0


async def get_plausibility_notes(
    project_id: UUID,
    db: AsyncSession,
) -> PlausibilityCheckResult:
    """Return all plausibility notes for a project."""
    stmt = (
        select(PlausibilityNote)
        .where(PlausibilityNote.project_id == project_id)
        .options(selectinload(PlausibilityNote.occurrences))
        .order_by(PlausibilityNote.created_at.asc())
    )
    result = await db.execute(stmt)
    notes = result.scalars().all()

    contradictions = []
    for note in notes:
        occurrences = [
            ContradictionOccurrence(
                document_id=occ.document_id,
                document_name=occ.document_name,
                content_excerpt=occ.content_excerpt,
                page_number=occ.page_number,
            )
            for occ in note.occurrences
        ]

        contradictions.append(
            Contradiction(
                id=note.id,
                description=note.description,
                status=PlausibilityNoteStatus(note.status),
                occurrences=occurrences,
            )
        )

    return PlausibilityCheckResult(contradictions=contradictions)
