from uuid import UUID

from temporalio import activity

from src.models.db.database import AsyncSessionLocal
from src.models.db.workflow_enum import ActionEnum, ErrorCode
from src.services.workflows.activities.activity_models import (
    DeleteFileInput,
    SingleFileResult,
)
from src.utils.service_utils import create_file_service


@activity.defn
async def delete_file(
    activity_input: DeleteFileInput,
) -> SingleFileResult:
    """Activity to delete a single file from DMS."""

    activity.logger.info(
        f"Delete file '{activity_input.filename}' "
        f"(file_id={activity_input.file_id}, "
        f"project={activity_input.project_id})"
    )

    try:
        async with AsyncSessionLocal() as db:
            service = await create_file_service(db=db)

            await service.delete_file(file_id=UUID(activity_input.file_id))

            return SingleFileResult(
                success=True,
                filename=activity_input.filename,
                file_id=activity_input.file_id,
                action=ActionEnum.DELETE,
            )
    except FileNotFoundError:
        return SingleFileResult(
            success=False,
            filename=activity_input.filename,
            error_code=ErrorCode.FILE_NOT_FOUND,
            error_message="File to delete not found in DMS",
            action=ActionEnum.DELETE,
        )
    except Exception as exc:
        activity.logger.error(
            f"Failed to delete file {activity_input.filename} "
            f"- {activity_input.file_id}: {exc}"
        )
        return SingleFileResult(
            success=False,
            filename=activity_input.filename,
            error_code=ErrorCode.DELETE_FAILED,
            error_message="Failed to delete file",
            action=ActionEnum.DELETE,
        )
