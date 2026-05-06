from uuid import UUID

from temporalio import activity

from src.models.db.database import AsyncSessionLocal
from src.models.db.workflow_enum import ActionEnum, ErrorCode
from src.models.schemas.file_schema import FileUpdateRequest
from src.services.workflows.activities.activity_models import (
    RenameFileInput,
    SingleFileResult,
)
from src.utils.service_utils import create_file_service


@activity.defn
async def rename_file(
    activity_input: RenameFileInput,
) -> SingleFileResult:
    """Activity to delete a single file from DMS."""

    activity.logger.info(
        f"Rename file '{activity_input.old_name}' to '{activity_input.new_name}' "
        f"(file_id={activity_input.file_id}, "
        f"project={activity_input.project_id})"
    )

    try:
        async with AsyncSessionLocal() as db:
            service = await create_file_service(db=db)

            file = await service.update_file(
                file_id=UUID(activity_input.file_id),
                update_data=FileUpdateRequest(  # type: ignore
                    filename=activity_input.new_name,
                ),
            )
            if not file:
                return SingleFileResult(
                    success=False,
                    filename=activity_input.new_name,
                    error_code=ErrorCode.FILE_NOT_FOUND,
                    error_message="File to rename not found in DMS",
                    action=ActionEnum.RENAME,
                )

            return SingleFileResult(
                success=True,
                filename=activity_input.new_name,
                file_id=activity_input.file_id,
                action=ActionEnum.RENAME,
            )
    except Exception as exc:
        activity.logger.error(
            f"Failed to rename file ({activity_input.file_id}) "
            f"{activity_input.old_name} to {activity_input.new_name}: {exc}"
        )
        return SingleFileResult(
            success=False,
            filename=activity_input.new_name,
            error_code=ErrorCode.RENAME_FAILED,
            error_message="Failed to rename file",
            action=ActionEnum.RENAME,
        )
