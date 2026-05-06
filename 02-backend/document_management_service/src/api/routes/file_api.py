from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.dependencies import get_file_service
from src.models.db.file_enum import FileTypeEnum
from src.models.schemas.file_schema import (
    FileDownloadResponse,
    FileResponse,
    FileUpdateRequest,
    FileUploadUrlResponse,
    StartFileProcessingRequest,
    StartFileProcessingResponse,
    UploadRequest,
    ZipFileResponse,
)
from src.services.files.file_service import FileService

router = APIRouter(prefix="/v2/files", tags=["Files"])


@router.post("/confirm-upload", response_model=FileResponse | ZipFileResponse)
async def confirm_upload(
    payload: UploadRequest,
    service: FileService = Depends(get_file_service),
):
    """
    Confirm that a file upload has completed and persist its metadata.

    Args:
        payload (UploadRequest): Metadata for the uploaded file
        service (FileService): FileService instance

    Returns:
        FileResponse | ZipFileResponse: Metadata of the confirmed file or zip file
    """
    created = await service.confirm_upload(file_data=payload)
    return created.__dict__


@router.get("/{file_id}", response_model=FileResponse)
async def get_file(
    file_id: UUID,
    service: FileService = Depends(get_file_service),
):
    """
    Retrieve a file by its UUID.

    Args:
        file_id (UUID): UUID of the file to retrieve
        service (FileService): FileService instance

    Returns:
        FileResponse: File metadata
    """
    file = await service.get_file(file_id=file_id)
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )
    return file.__dict__


@router.get("/{file_id}/versions", response_model=list[FileResponse])
async def get_versions(
    file_id: UUID,
    service: FileService = Depends(get_file_service),
):
    """
    Retrieve all versions of a file by its UUID.

    Args:
        file_id (UUID): UUID of the file versions to retrieve
        service (FileService): FileService instance

    Returns:
        list[FileResponse]: List of file metadata
    """
    files = await service.get_versions(file_id=file_id)
    if not files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )
    return [file.__dict__ for file in files]


@router.patch("/{file_id}", response_model=FileResponse)
async def update_file(
    file_id: UUID,
    payload: FileUpdateRequest,
    service: FileService = Depends(get_file_service),
):
    """
    Update fields of an existing file.

    Args:
        file_id (UUID): UUID of the file to update
        payload (FileUpdateRequest): Data to update on the file
        service (FileService): FileService instance

    Returns:
        FileResponse: The updated file metadata
    """
    updated = await service.update_file(file_id=file_id, update_data=payload)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )
    return updated.__dict__


@router.delete("/{file_id}", response_model=FileResponse)
async def delete_file(
    file_id: UUID,
    soft: bool = True,
    service: FileService = Depends(get_file_service),
):
    """
    Soft delete a file by its UUID.

    Args:
        file_id (UUID): UUID of the file to delete
        soft (bool): Delete files soft. Defaults to True
        service (FileService): FileService instance

    Returns:
        FileResponse: Metadata of the deleted file
    """
    file = await service.delete_file(
        file_id=file_id,
        soft=soft,
    )
    return file.__dict__


@router.get("/{file_id}/generate-download-url", response_model=FileDownloadResponse)
async def generate_download_url(
    file_id: UUID,
    inline: Annotated[bool, Query()] = False,
    include_deleted: Annotated[bool, Query(alias="includeDeleted")] = False,
    service: FileService = Depends(get_file_service),
):
    """
    Generate a signed URL to download a file by its UUID.

    Args:
        file_id (UUID): UUID of the file to download
        inline (bool, optional): If True, the file will be displayed inline
            in the browser.
        include_deleted (bool): If True, allows to download soft deleted files
        service (FileService): FileService instance

    Returns:
        FileDownloadResponse: File metadata with a signed download URL
    """
    file, url = await service.generate_download_url(
        file_id=file_id,
        inline=inline,
        include_deleted=include_deleted,
    )
    return FileDownloadResponse(download_url=url)


@router.post("/start-file-processing", response_model=StartFileProcessingResponse)
async def start_file_processing(
    payload: StartFileProcessingRequest,
    service: FileService = Depends(get_file_service),
):
    """
    Start a Temporal file-processing workflow for an uploaded ZIP.

    The ZIP row is inferred from `file_id` + `project_id` and then extracted so each
    contained file is processed individually.
    """
    return await service.start_file_processing(payload)


@router.post("/generate-upload-url", response_model=FileUploadUrlResponse)
async def generate_upload_url(
    file_data: UploadRequest,
    service: FileService = Depends(get_file_service),
):
    """
    Generate a signed URL to upload a file.

    Args:
        file_data (UploadRequest): Name of the file
        service (FileService): FileService instance

    Returns:
        FileUploadUrlResponse: Signed upload URL and MIME type
    """
    url, mime_type = await service.generate_upload_url(file_data=file_data)

    return FileUploadUrlResponse(
        upload_url=url,
        mime_type=mime_type,
    )


@router.get("", response_model=list[FileResponse])
async def list_files(
    file_type: FileTypeEnum,
    project_id: Annotated[UUID | None, Query(alias="projectId")] = None,
    name: Annotated[
        str | None,
        Query(description="Optional search string for filename (SQL ilike)"),
    ] = None,
    path: Annotated[
        str | None,
        Query(description="Optional search string for bucket path (contains)"),
    ] = None,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 50,
    service: FileService = Depends(get_file_service),
):
    """
    Get a list of all files.

    Args:
        file_type (FileTypeEnum): File type
        project_id (UUID | None): Optional project filter
        name (str | None): Optional name filter
        path (str | None): Optional path filter
        page_size (int): Optional page size
        page (int): Optional page number
        service (FileService): FileService instance

    Returns:
        list[FileResponse]: List of files matching filters
    """
    files = await service.list_files(
        project_id=project_id,
        name=name,
        path=path,
        file_type=file_type,
        page=page,
        page_size=page_size,
    )
    return [file.__dict__ for file in files]
