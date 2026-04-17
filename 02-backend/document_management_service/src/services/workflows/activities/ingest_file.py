from uuid import UUID

from temporalio import activity

from src.models.db.database import AsyncSessionLocal
from src.models.db.workflow_enum import ActionEnum, ErrorCode
from src.services.workflows.activities.activity_models import (
    IngestFileInput,
    SingleFileResult,
)
from src.utils.service_utils import create_file_service


@activity.defn
async def ingest_file(
    activity_input: IngestFileInput,
) -> SingleFileResult:
    """Activity to ingest a single file into DMS."""

    activity.logger.info(
        f"Ingest file '{activity_input.filename}' "
        f"(bucket_path={activity_input.bucket_path}, "
        f"project={activity_input.project_id})"
    )
    zip_file_id = UUID(activity_input.zip_file_id)
    project_id = UUID(activity_input.project_id)

    try:
        async with AsyncSessionLocal() as db:
            service = await create_file_service(db=db)

            created = await service.ingest_zip_entry_document(
                source_zip_file_id=zip_file_id,
                project_id=project_id,
                filename=activity_input.filename,
                bucket_path=activity_input.bucket_path,
            )

            return SingleFileResult(
                success=True,
                filename=activity_input.filename,
                file_id=str(created.id),
                action=ActionEnum.INGEST,
            )
    except FileNotFoundError:
        return SingleFileResult(
            success=False,
            filename=activity_input.filename,
            error_code=ErrorCode.FILE_NOT_FOUND,
            error_message="File to move into DMS not found in storage",
            action=ActionEnum.INGEST,
        )
    except Exception as exc:
        activity.logger.error(f"Failed to ingest file {activity_input.filename}: {exc}")
        return SingleFileResult(
            success=False,
            filename=activity_input.filename,
            error_code=ErrorCode.UPLOAD_FAILED,
            error_message="Failed to ingest file",
            action=ActionEnum.INGEST,
        )
