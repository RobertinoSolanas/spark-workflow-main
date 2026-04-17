import asyncio
import zipfile
from io import BytesIO
from uuid import UUID

from temporalio import activity

from src.config.settings import settings
from src.models.db.database import AsyncSessionLocal
from src.models.db.workflow_enum import ActionEnum, ErrorCode
from src.services.files.file_service import FileService
from src.services.files.file_validation import validate_file_upload
from src.services.workflows.activities.activity_models import (
    ExtractZipInput,
    SingleFileResult,
)
from src.services.workflows.activities.activity_utils import _create_s3fs, _get_s3_path
from src.services.zip_utils import _normalize_zip_entry_name, validate_zip_metadata
from src.utils.exceptions import (
    FileInvalidFileExtensionError,
    FileInvalidFileTypeError,
)
from src.utils.service_utils import create_file_service


@activity.defn
async def extract_zip(
    activity_input: ExtractZipInput,
) -> list[SingleFileResult]:
    """Extract a ZIP from S3 via s3fs + zipfile and ingest each valid entry.

    Processes entries one-by-one to keep memory usage bounded to a single file.
    """
    activity.logger.info(
        f"Processing zip '{activity_input.filename}' "
        f"(zip_id={activity_input.zip_file_id}, project={activity_input.project_id})"
    )

    project_id = UUID(activity_input.project_id)
    s3_path = _get_s3_path(activity_input.zip_path)

    results: list[SingleFileResult] = []

    try:
        fs = _create_s3fs()

        # 1. Get metadata in a thread
        def _get_zip_metadata():
            with fs.open(s3_path, "rb") as f:
                with zipfile.ZipFile(f) as zf:
                    return validate_zip_metadata(
                        zf=zf, zip_filename=activity_input.filename
                    )

        valid_entries = await asyncio.to_thread(_get_zip_metadata)

        async with AsyncSessionLocal() as db:
            service: FileService = await create_file_service(db=db)

            for entry in valid_entries:
                relative_filename = _normalize_zip_entry_name(entry.filename)
                if not relative_filename:
                    continue

                def _read_entry(entry_info):
                    with fs.open(s3_path, "rb") as f:
                        with zipfile.ZipFile(f) as zf:
                            return zf.read(entry_info)

                try:
                    entry_content = await asyncio.to_thread(_read_entry, entry)
                    mime_type = validate_file_upload(
                        filename=relative_filename,
                        allowed_extensions=settings.ALLOWED_FILE_EXTENSIONS,
                        allowed_mime_types=settings.ALLOWED_FILE_TYPES,
                        content_bytes=entry_content,
                    )

                    file_path = f"tmp/{project_id}/{relative_filename}"
                    if not await service.storage_provider_service.document_exists(
                        document_name=file_path
                    ):
                        sha256 = await service.storage_provider_service.compute_sha256(
                            source=BytesIO(entry_content),
                        )
                        await service.storage_provider_service.upload_document_from_obj(
                            document_name=file_path,
                            file_obj=BytesIO(entry_content),
                            mime_type=mime_type,
                            metadata={"sha256": sha256},
                        )

                    results.append(
                        SingleFileResult(
                            success=True,
                            filename=relative_filename,
                            bucket_path=file_path,
                            action=ActionEnum.UNZIP,
                        )
                    )
                except (
                    FileInvalidFileExtensionError,
                    FileInvalidFileTypeError,
                ) as exc:
                    results.append(
                        SingleFileResult(
                            success=False,
                            filename=relative_filename,
                            error_code=ErrorCode.VALIDATION_FAILED,
                            error_message=str(exc),
                            action=ActionEnum.UNZIP,
                        )
                    )
                finally:
                    # Explicitly clear entry_content for GC
                    entry_content = b""
    except FileNotFoundError:
        return [
            SingleFileResult(
                success=False,
                filename=activity_input.filename,
                bucket_path=activity_input.zip_path,
                error_code=ErrorCode.ZIP_NOT_FOUND,
                error_message="Zip file not found in storage",
                action=ActionEnum.UNZIP,
            )
        ]
    except (zipfile.BadZipFile, ValueError) as exc:
        return [
            SingleFileResult(
                success=False,
                filename=activity_input.filename,
                error_code=ErrorCode.ZIP_INVALID,
                error_message=str(exc),
                action=ActionEnum.UNZIP,
            )
        ]

    succeeded = len([r for r in results if r.success])
    failed = len(results) - succeeded
    activity.logger.info(
        f"Zip processing complete: {succeeded} succeeded, {failed} failed"
    )
    return results
