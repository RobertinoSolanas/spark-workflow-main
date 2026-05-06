from uuid import UUID

from sqlalchemy import select
from temporalio import activity

from src.models.db.database import AsyncSessionLocal
from src.models.db.db_models import ZipFile
from src.models.db.workflow_enum import WorkflowStatusEnum
from src.services.workflows.activities.activity_models import UpdateFileStatusInput


def _parse_workflow_status(status_raw: str) -> WorkflowStatusEnum:
    """Parse status by direct enum cast (no normalization)."""
    status_clean = status_raw.strip()
    if not status_clean:
        raise ValueError("Workflow status is required.")

    return WorkflowStatusEnum(status_clean)


@activity.defn
async def update_file_status(activity_input: UpdateFileStatusInput) -> None:
    """Update workflow status of a ZIP row."""
    workflow_status = _parse_workflow_status(activity_input.status)
    zip_file_id = UUID(activity_input.zip_file_id)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ZipFile).where(ZipFile.id == zip_file_id).limit(1)
        )
        zip_file = result.scalar_one_or_none()
        if zip_file is None:
            raise FileNotFoundError(f"Zip file '{zip_file_id}' not found.")

        zip_file.workflow_status = workflow_status
        await db.commit()
