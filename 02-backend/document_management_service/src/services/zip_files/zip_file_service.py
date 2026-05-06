from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.models.db.db_models import ZipFile
from src.models.db.workflow_enum import WorkflowStatusEnum
from src.services.storage_provider.storage_provider_base_service import (
    BaseStorageProviderService,
)


class ZipFileService:
    """Service class for querying zip file metadata."""

    def __init__(
        self,
        db: AsyncSession,
        storage_provider_service: BaseStorageProviderService,
    ):
        self.db = db
        self.storage_provider_service = storage_provider_service

    async def get_zip_file(self, zip_file_id: UUID) -> ZipFile | None:
        """Retrieve a zip file by its UUID."""
        result = await self.db.execute(select(ZipFile).where(ZipFile.id == zip_file_id))
        return result.scalar_one_or_none()

    async def update_zip_workflow_status(
        self,
        zip_file_id: UUID,
        status: WorkflowStatusEnum,
    ) -> ZipFile:
        """Update and persist workflow status for a ZIP file row."""
        result = await self.db.execute(
            select(ZipFile).where(ZipFile.id == zip_file_id).limit(1)
        )
        zip_file = result.scalar_one_or_none()
        if zip_file is None:
            raise FileNotFoundError(f"Zip file '{zip_file_id}' not found.")

        zip_file.workflow_status = status
        await self.db.commit()
        await self.db.refresh(zip_file)
        return zip_file

    async def list_zip_files(
        self,
        project_id: UUID | None = None,
        workflow_status: WorkflowStatusEnum | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Sequence[ZipFile]:
        """Filtered list of zip files, ordered by created_at desc."""
        offset = (page - 1) * page_size

        conditions = []

        if project_id is not None:
            conditions.append(ZipFile.project_id == project_id)

        if workflow_status is not None:
            conditions.append(ZipFile.workflow_status == workflow_status)

        query = (
            select(ZipFile)
            .order_by(ZipFile.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )

        if conditions:
            query = query.where(and_(*conditions))

        result = await self.db.execute(query)
        return result.scalars().all()
