from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.dependencies import get_zip_file_service
from src.models.db.workflow_enum import WorkflowStatusEnum
from src.models.schemas.file_schema import ZipFileResponse
from src.services.zip_files.zip_file_service import ZipFileService

router = APIRouter(prefix="/v2/zip-files", tags=["Zip Files"])


@router.get("", response_model=list[ZipFileResponse])
async def list_zip_files(
    project_id: Annotated[UUID | None, Query(alias="projectId")] = None,
    workflow_status: Annotated[
        WorkflowStatusEnum | None, Query(alias="workflowStatus")
    ] = None,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 50,
    service: ZipFileService = Depends(get_zip_file_service),
):
    """List zip files with optional project and workflow status filtering."""
    zip_files = await service.list_zip_files(
        project_id=project_id,
        workflow_status=workflow_status,
        page=page,
        page_size=page_size,
    )
    return [zf.__dict__ for zf in zip_files]


@router.get("/{zip_file_id}", response_model=ZipFileResponse)
async def get_zip_file(
    zip_file_id: UUID,
    service: ZipFileService = Depends(get_zip_file_service),
):
    """Retrieve a zip file by its UUID."""
    zip_file = await service.get_zip_file(zip_file_id=zip_file_id)
    if not zip_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Zip file not found",
        )
    return zip_file.__dict__
