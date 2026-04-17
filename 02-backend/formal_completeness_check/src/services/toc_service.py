"""Service layer for table of content notes CRUD operations."""

from uuid import UUID

import httpx
from event_logging.enums import (
    EventAction,
    EventCategory,
    EventOutcome,
    LogEventDefault,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, retry_if_exception_type, stop_after_attempt

from src.config.settings import settings
from src.exceptions.exceptions import NotFoundError
from src.models.db_models import TableOfContentNotes
from src.models.schemas.fcs_types import FileDownloadResponse
from src.models.schemas.toc_schemas import (
    CreateTableContentNoteRequest,
    TableContentNotesResponse,
    TocJobDoneResponse,
    TocResults,
)
from src.utils.logger import logger


async def get_toc_notes_for_project(
    project_id: UUID,
    db: AsyncSession,
) -> list[TableContentNotesResponse]:
    """Return all table of content notes for a project, ordered by newest first."""
    stmt = (
        select(TableOfContentNotes)
        .where(TableOfContentNotes.project_id == project_id)
        .order_by(TableOfContentNotes.created_at.desc())
    )
    result = await db.execute(stmt)
    return [
        TableContentNotesResponse.model_validate(note)
        for note in result.scalars().all()
    ]


async def create_toc_notes(
    project_id: UUID,
    payloads: list[CreateTableContentNoteRequest],
    db: AsyncSession,
) -> list[TableContentNotesResponse]:
    """Create multiple table of content notes for a project in a single transaction."""
    logger.info(
        EventAction.WRITE,
        EventOutcome.UNKNOWN,
        EventCategory.DATABASE,
        default_event=LogEventDefault.DB_WRITE,
        message=f"Creating {len(payloads)} TOC notes for project_id={project_id}",
    )

    notes = [
        TableOfContentNotes(project_id=project_id, content=payload.content)
        for payload in payloads
    ]
    db.add_all(notes)
    await db.flush()
    await db.commit()

    logger.info(
        EventAction.WRITE,
        EventOutcome.SUCCESS,
        EventCategory.DATABASE,
        default_event=LogEventDefault.DB_WRITE,
        message=f"Successfully created {len(notes)} TOC notes for project_id={project_id}",
    )

    return [TableContentNotesResponse.model_validate(note) for note in notes]


async def update_toc_note_resolved_status(
    project_id: UUID,
    note_id: UUID,
    is_resolved: bool,
    db: AsyncSession,
) -> TableContentNotesResponse:
    """Update the resolved status of a table of content note."""
    logger.info(
        EventAction.CHANGE,
        EventOutcome.UNKNOWN,
        EventCategory.DATABASE,
        default_event=LogEventDefault.DB_WRITE,
        message=f"Updating TOC note id={note_id} for project_id={project_id}",
    )

    stmt = select(TableOfContentNotes).where(
        TableOfContentNotes.id == note_id,
        TableOfContentNotes.project_id == project_id,
    )
    result = await db.execute(stmt)
    note = result.scalar_one_or_none()

    if note is None:
        raise NotFoundError(
            f"TOC note with id={note_id} not found for project_id={project_id}"
        )

    note.is_resolved = is_resolved
    await db.commit()

    logger.info(
        EventAction.CHANGE,
        EventOutcome.SUCCESS,
        EventCategory.DATABASE,
        default_event=LogEventDefault.DB_WRITE,
        message=f"Successfully updated TOC note id={note_id} for project_id={project_id}",
    )

    return TableContentNotesResponse.model_validate(note)


@retry(
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException)),
)
async def _fetch_toc_results(file_id: UUID) -> TocResults:
    """Fetch TOC results from DMS using a single HTTP client for both requests."""
    download_url_endpoint = f"{settings.DOCUMENT_MANAGEMENT_SERVICE_URL}/v2/files/{file_id}/generate-download-url"

    logger.info(
        EventAction.READ,
        EventOutcome.UNKNOWN,
        EventCategory.API,
        default_event=LogEventDefault.EXTERNAL_SERVICE_INTERACTION,
        message=f"Fetching TOC results download URL for file_id={file_id}",
    )

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(download_url_endpoint)
        response.raise_for_status()
        download_info = FileDownloadResponse.model_validate(response.json())

        logger.debug(
            EventAction.READ,
            EventOutcome.SUCCESS,
            EventCategory.API,
            default_event=LogEventDefault.EXTERNAL_SERVICE_INTERACTION,
            message=f"Obtained presigned download URL for file_id={file_id}",
        )

        response = await client.get(
            download_info.download_url,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        return TocResults.model_validate_json(response.content)


async def _save_toc_notes(
    project_id: UUID,
    matched_types: list,
    db: AsyncSession,
) -> list[str]:
    """Process fetched results and save matched document types as TOC notes.

    Returns the list of unmatched document type names that were saved as notes.
    """
    logger.info(
        EventAction.READ,
        EventOutcome.SUCCESS,
        EventCategory.API,
        default_event=LogEventDefault.EXTERNAL_SERVICE_INTERACTION,
        message=f"Fetched {len(matched_types)} matched document types for project_id={project_id}",
    )

    unmatched = [mt for mt in matched_types if not mt.assigned_documents]
    notes = [
        TableOfContentNotes(
            project_id=project_id,
            content=mt.required_document_type.document_type_name,
        )
        for mt in unmatched
    ]

    try:
        db.add_all(notes)
        await db.commit()
    except Exception as e:
        logger.error(
            EventAction.WRITE,
            EventOutcome.FAILURE,
            EventCategory.DATABASE,
            default_event=LogEventDefault.DB_WRITE,
            message=f"Failed to save TOC notes for project_id={project_id}: {str(e)}",
        )
        raise

    logger.info(
        EventAction.WRITE,
        EventOutcome.SUCCESS,
        EventCategory.DATABASE,
        default_event=LogEventDefault.DB_WRITE,
        message=f"Created {len(notes)} TOC notes for project_id={project_id}",
    )

    return [mt.required_document_type.document_type_name for mt in unmatched]


async def process_toc_job_results(
    project_id: UUID,
    file_id: UUID,
    db: AsyncSession,
) -> TocJobDoneResponse:
    """Fetch toc notes results from DMS and append matched document type names as notes."""
    results = await _fetch_toc_results(file_id)
    matched_types = results.inhaltsverzeichnis_matching_output.matched_document_types
    unmatched_names = await _save_toc_notes(project_id, matched_types, db)

    if not matched_types:
        status = "no_document_types_found"
    elif not unmatched_names:
        status = "all_document_types_matched"
    else:
        status = "missing_documents_found"

    return TocJobDoneResponse(
        status=status,
        notes_created=len(unmatched_names),
        matched_document_types_total=len(matched_types),
        unmatched_document_types=unmatched_names,
    )
