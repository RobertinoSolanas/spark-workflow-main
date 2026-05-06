from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from event_logging.enums import (
    EventAction,
    EventCategory,
    EventOutcome,
    LogEventDefault,
)
from sqlalchemy import and_, delete, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.sql.functions import func

from src.config.settings import settings
from src.models.db.db_models import File, ZipFile
from src.models.db.file_enum import FileTypeEnum
from src.models.db.workflow_enum import WorkflowEnum, WorkflowStatusEnum
from src.models.schemas.file_schema import (
    FileUpdateRequest,
    ProjectDocumentUpload,
    StartFileProcessingRequest,
    StartFileProcessingResponse,
    UploadRequest,
)
from src.services.files.file_validation import validate_file_upload
from src.services.files.path_builder.path_builder_base import FileContext
from src.services.files.path_builder.path_builder_factory import PathBuilderFactory
from src.services.storage_provider.storage_provider_base_service import (
    BaseStorageProviderService,
)
from src.services.temporal.temporal_service import TemporalWorkflowService
from src.utils.exceptions import (
    WorkflowInRunningStateError,
    WorkflowRequiresApprovalError,
)
from src.utils.logger import logger


class FileService:
    """Service class for managing files in object storage and the database."""

    def __init__(
        self,
        db: AsyncSession,
        storage_provider_service: BaseStorageProviderService,
        temporal_workflow_service: TemporalWorkflowService,
    ):
        """
        Args:
            db: Async SQLAlchemy session.
            storage_provider_service: BaseStorageProviderService
                instance (for mocking/testing).
            temporal_workflow_service: TemporalWorkflowService instance for interacting
                with the temporal.
        """
        self.db = db
        self.storage_provider_service = storage_provider_service
        self.temporal_workflow_service = temporal_workflow_service

    @staticmethod
    def _get_object_path(
        filename: str,
        context: UploadRequest,
        version: int,
    ) -> str:
        """
        Create the object path from filename and context.

        Args:
            filename (str): The name of the file.
            context (UploadRequest): The context of the file,
                containing additional path information.
            version (int): The version number to use in the path.

        Returns:
            str: The object path with cleaned filename.
        """
        return str(
            PathBuilderFactory.build_path(
                filename=filename,
                context=FileContext(**context.model_dump(), version=version),
            )
        )

    async def _get_latest_version(
        self,
        file_data: UploadRequest,
    ) -> tuple[File | None, int]:
        """
        Retrieve the latest non-deleted version of a file by filename and
        optional project scope.

        Args:
            file_data (UploadRequest): The pydatic model of the
                uploaded file.

        Returns:
            A tuple containing:
            - The latest non-deleted File record
              (or None if no non-deleted version exists).
            - The version number that should be used for the next upload
              (always max_version + 1, or 1 if none exist).
        """
        # Build the base conditions for filename and project scoping
        file_dump = file_data.model_dump(by_alias=False)

        optional_fields = {
            "project_id": File.project_id,
            "workflow_id": File.workflow_id,
            "run_id": File.run_id,
        }
        conditions = [
            File.filename == file_data.filename,
            File.type == file_data.type,
        ]
        for key, col in optional_fields.items():
            if key in file_dump and file_dump[key] is not None:
                conditions.append(col == file_dump[key])
            elif key in file_dump:
                conditions.append(col.is_(None))

        # Get the highest version number that matches the criteria
        max_version_result = await self.db.execute(
            select(func.max(File.version)).where(and_(*conditions))
        )
        max_version: int | None = max_version_result.scalar_one_or_none()

        next_version = (max_version or 0) + 1

        # Fetch the latest non-deleted record (if any) for returning the File object
        latest_file_result = await self.db.execute(
            select(File)
            .where(and_(*conditions, File.deleted.is_(False)))
            .order_by(File.version.desc())
            .limit(1)
        )
        latest_file: File | None = latest_file_result.scalar_one_or_none()

        return latest_file, next_version

    @staticmethod
    async def _build_file_record(
        file_data: UploadRequest,
        bucket_path: str,
        version: int,
        mime_type: str | None = None,
        source_zip_file_id: UUID | None = None,
    ) -> File | ZipFile:
        """
        Maps any UploadRequest to a Files DB model.

        Args:
            file_data (UploadRequest): The Pydantic model of the
                uploaded file.
            bucket_path: The path of the file in the bucket.
            version (int): The version number of the file.
            mime_type (str | None): The MIME type of the file.
            source_zip_file_id (UUID | None): The ID of the source zip file.

        Returns:
            File | ZipFile: The database file or zip file record.
        """
        if file_data.type == FileTypeEnum.ZIP:
            return ZipFile(
                filename=file_data.filename,
                bucket_path=bucket_path,
                project_id=getattr(file_data, "project_id", None),
                workflow_status=WorkflowStatusEnum.PENDING,
            )
        else:
            return File(
                # Required
                type=FileTypeEnum(file_data.type),
                filename=file_data.filename,
                mime_type=mime_type,
                bucket_path=bucket_path,
                version=version,
                # Optional
                project_id=getattr(file_data, "project_id", None),
                run_id=getattr(file_data, "run_id", None),
                workflow_id=getattr(file_data, "workflow_id", None),
                vector_searchable=getattr(file_data, "vector_searchable", None),
                source_zip_file_id=source_zip_file_id,
            )

    async def _prepare_version_and_check_conflict(
        self,
        file_data: UploadRequest,
    ) -> tuple[File | None, int]:
        """Determine the next version number and check for filename conflicts.

        Retrieves the latest non-deleted file record (if any) for the given filename
        and project scope, then computes the next version number.

        If a file already exists and `create_new_version` is False, raises an error
        to prevent overwriting/duplication.

        Args:
            file_data (UploadRequest): The Pydantic model of the
                uploaded file.

        Returns:
            A tuple containing:
            - The latest non-deleted File record (or None if no existing file)
            - The next version number to use (1 if none exist, otherwise max+1)

        Raises:
            FileExistsError: If a file already exists and create_new_version is False.
        """
        existing_file, next_version = await self._get_latest_version(
            file_data=file_data
        )

        if existing_file is not None and not file_data.create_new_version:
            raise FileExistsError(
                f"File '{file_data.filename}' already exists "
                f"(latest version {existing_file.version}). "
                f"Pass create_new_version=True to create a new version instead."
            )

        return existing_file, next_version

    @staticmethod
    async def _mark_previous_as_deleted(
        existing_file: File | None,
        next_version: int,
    ) -> None:
        """Soft-delete the previous version of a file if it exists.

        Marks the existing file record as deleted (deleted=True) and logs the action.

        Args:
            existing_file: The previous non-deleted File record (or None).
            next_version: The version number of the new file being created.
        """
        if not existing_file:
            return

        existing_file.deleted = True
        logger.info(
            action=EventAction.UPLOAD,
            outcome=EventOutcome.SUCCESS,
            category=EventCategory.FILE,
            default_event=LogEventDefault.DOCUMENT_UPLOAD,
            file_id=str(existing_file.id),
            file_path=existing_file.bucket_path,
            message=(
                f"Marked previous file (v{existing_file.version}) "
                f"as deleted for new version {next_version}"
            ),
        )

    async def _create_and_commit_file_record(
        self,
        file_data: UploadRequest,
        bucket_path: str,
        mime_type: str,
        version: int,
        source_zip_file_id: UUID | None = None,
        file_size: int | None = None,
    ) -> File | ZipFile:
        """Create, persist, and refresh a new File (or ZipFile) record in the database.

        Builds the record using _build_file_record, adds it to the session,
        commits the transaction, and refreshes the object.

        On any exception:
        - Rolls back the transaction
        - Attempts to delete the uploaded object from storage
        - Re-raises the original exception

        Args:
            file_data: Validated upload request data.
            bucket_path: Full relative path where the file was/will be stored.
            mime_type: MIME type of the uploaded file.
            version: Version number assigned to this file record.
            source_zip_file_id: Optional ID of the source ZIP file this file came from.
            file_size: Optional file size in bytes for structured logging.

        Returns:
            The newly created and refreshed File or ZipFile database object.

        Raises:
            Exception: Any database or unexpected error during commit (after cleanup).
        """
        file_record = await self._build_file_record(
            file_data=file_data,
            bucket_path=bucket_path,
            mime_type=mime_type,
            version=version,
            source_zip_file_id=source_zip_file_id,
        )

        try:
            self.db.add(file_record)
            await self.db.commit()
            await self.db.refresh(file_record)
            logger.info(
                action=EventAction.UPLOAD,
                outcome=EventOutcome.SUCCESS,
                category=EventCategory.FILE,
                file_id=str(file_record.id),
                file_path=bucket_path,
                file_name=file_data.filename,
                file_size=file_size,
                message="Successfully created new file record.",
            )
            return file_record
        except Exception as exc:
            await self.db.rollback()
            try:
                await self.storage_provider_service.delete_document(
                    document_name=bucket_path
                )
                logger.warn(
                    action=EventAction.DELETE,
                    outcome=EventOutcome.FAILURE,
                    category=EventCategory.FILE,
                    file_path=bucket_path,
                    message="Cleaned up failed upload object.",
                )
            except Exception as e:
                logger.error(
                    action=EventAction.DELETE,
                    outcome=EventOutcome.FAILURE,
                    category=EventCategory.FILE,
                    file_path=bucket_path,
                    message=f"Cleanup failed after rollback: {e}",
                )
            raise exc

    async def confirm_upload(self, file_data: UploadRequest) -> File | ZipFile:
        """Confirm a file was uploaded via signed URL and create its metadata record.

        Verifies the file exists in storage, checks for existing versions,
        soft-deletes any previous version if applicable, and creates the new record.

        If a file with the same name already exists and create_new_version is False,
        raises FileExistsError.

        Args:
            file_data: Upload request metadata (filename, type, etc.) for a
                pre-uploaded file.

        Returns:
            The newly created File or ZipFile database object.

        Raises:
            FileNotFoundError: If the file does not exist in storage at
                the expected path.
            FileExistsError: If file exists and create_new_version=False.
            ValueError: If MIME type cannot be determined.
            Exception: Any database error (with cleanup on failure).
        """
        # Check version & conflict
        existing_file, version = await self._prepare_version_and_check_conflict(
            file_data=file_data
        )

        # Verify file exists in storage
        bucket_path = self._get_object_path(
            filename=file_data.filename,
            context=file_data,
            version=version,
        )

        # Check if file exists in S3
        if not await self.storage_provider_service.document_exists(
            document_name=bucket_path
        ):
            raise FileNotFoundError(
                f"Uploaded file not found in storage: {bucket_path}"
            )

        mime_type = await self.storage_provider_service.get_file_mime_type(
            document_name=bucket_path
        )

        # Delete previous version
        await self._mark_previous_as_deleted(
            existing_file=existing_file,
            next_version=version,
        )

        return await self._create_and_commit_file_record(
            file_data=file_data,
            bucket_path=bucket_path,
            mime_type=mime_type,
            version=version,
        )

    async def _get_reserved_zip_entry_file(
        self,
        *,
        project_id: UUID,
        filename: str,
        source_zip_file_id: UUID,
    ) -> File | None:
        """Return already reserved/finalized file row for one ZIP entry, if present."""
        result = await self.db.execute(
            select(File)
            .where(
                File.project_id == project_id,
                File.type == FileTypeEnum.DOCUMENT,
                File.filename == filename,
                File.source_zip_file_id == source_zip_file_id,
            )
            .order_by(File.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _reserve_zip_entry_version(
        self,
        *,
        project_id: UUID,
        filename: str,
        source_zip_file_id: UUID,
        mime_type: str,
    ) -> File:
        """Create (or re-use on race) a deterministic reservation row for ZIP entry."""
        upload_ctx = ProjectDocumentUpload(
            type=FileTypeEnum.DOCUMENT,
            project_id=project_id,
            filename=filename,
            create_new_version=True,
        )
        _existing_latest, next_version = await self._get_latest_version(upload_ctx)
        bucket_path = self._get_object_path(
            filename=filename,
            context=upload_ctx,
            version=next_version,
        )

        reservation = File(
            type=FileTypeEnum.DOCUMENT,
            filename=filename,
            mime_type=mime_type,
            bucket_path=bucket_path,
            version=next_version,
            project_id=project_id,
            source_zip_file_id=source_zip_file_id,
            deleted=True,
        )

        try:
            self.db.add(reservation)
            await self.db.commit()
            await self.db.refresh(reservation)
            return reservation
        except IntegrityError:
            await self.db.rollback()
            existing = await self._get_reserved_zip_entry_file(
                project_id=project_id,
                filename=filename,
                source_zip_file_id=source_zip_file_id,
            )
            if existing is None:
                raise
            return existing

    async def ingest_zip_entry_document(
        self,
        *,
        source_zip_file_id: UUID,
        project_id: UUID,
        filename: str,
        bucket_path: str,
    ) -> File:
        """Idempotently ingest one document entry from a ZIP file."""
        reserved = await self._get_reserved_zip_entry_file(
            project_id=project_id,
            filename=filename,
            source_zip_file_id=source_zip_file_id,
        )
        mime_type = await self.storage_provider_service.get_file_mime_type(
            document_name=bucket_path
        )

        if reserved is None:
            reserved = await self._reserve_zip_entry_version(
                project_id=project_id,
                filename=filename,
                source_zip_file_id=source_zip_file_id,
                mime_type=mime_type,
            )
        elif reserved.mime_type != mime_type:
            reserved.mime_type = mime_type
            await self.db.commit()
            await self.db.refresh(reserved)

        if not await self.storage_provider_service.document_exists(
            document_name=reserved.bucket_path
        ):
            await self.storage_provider_service.copy_document(
                source_name=bucket_path,
                destination_name=reserved.bucket_path,
            )
            logger.info(
                action=EventAction.UPLOAD,
                outcome=EventOutcome.SUCCESS,
                category=EventCategory.FILE,
                file_id=str(reserved.id),
                file_path=bucket_path,
                file_name=reserved.filename,
                message=(
                    f"Successfully copied file {reserved.filename} "
                    f"from ZIP file {source_zip_file_id}."
                ),
            )
        else:
            logger.info(
                action=EventAction.UPLOAD,
                outcome=EventOutcome.SUCCESS,
                category=EventCategory.FILE,
                file_id=str(reserved.id),
                file_path=bucket_path,
                file_name=reserved.filename,
                message=(
                    f"File {reserved.filename} from ZIP file {source_zip_file_id} "
                    f"already exists. Skipping upload."
                ),
            )

        if reserved.deleted:
            await self.db.execute(
                update(File)
                .where(
                    File.project_id == project_id,
                    File.type == FileTypeEnum.DOCUMENT,
                    File.filename == filename,
                    File.deleted.is_(False),
                    File.id != reserved.id,
                )
                .values(deleted=True)
            )
            reserved.deleted = False
            await self.db.commit()
            await self.db.refresh(reserved)

        return reserved

    async def get_file(
        self,
        file_id: UUID,
        include_deleted: bool = False,
    ) -> File | None:
        """
        Retrieve a file by its UUID.

        Args:
            file_id (UUID): The unique ID of the file.
            include_deleted (bool): If True, include soft-deleted files.

        Returns:
            File | None: The File DB object if found, otherwise None.
        """
        conditions = [File.id == file_id]
        if not include_deleted:
            conditions.append(File.deleted == False)  # noqa: E712

        result = await self.db.execute(select(File).where(and_(*conditions)))
        file_record = result.scalar_one_or_none()

        return file_record

    async def get_versions(
        self,
        file_id: UUID,
    ) -> Sequence[File]:
        """
        Retrieve all versions of a file by its UUID (any version's ID).

        Returns:
            Sequence[File]: All versions of the file, ordered by version number
                descending. Returns empty list if no file found.
        """
        result = await self.db.execute(select(File).where(File.id == file_id))
        current = result.scalar_one_or_none()

        if not current:
            return []

        conditions = [
            File.project_id == current.project_id,
            File.filename == current.filename,
            File.type == current.type,
        ]

        result = await self.db.execute(
            select(File).where(and_(*conditions)).order_by(File.version.desc())
        )

        versions = result.scalars().all()
        return versions

    async def list_files(
        self,
        project_id: UUID | None = None,
        name: str | None = None,
        path: str | None = None,
        file_type: FileTypeEnum | None = None,
        page: int = 1,
        page_size: int | None = 50,
        include_deleted: bool = False,
    ) -> Sequence[File]:
        """
        List all files for a project, optionally filtered by file name.

        Args:
            file_type:
            project_id (UUID | None): Optional UUID of the project.
            name (str | None): Optional search string for filename (SQL ilike).
            path (str | None): Optional search string for bucket path (contains).
            page (int): Optional page number for paging.
            page_size(int): Optional page size for paging.
            include_deleted (bool): If True, include soft-deleted files.

        Returns:
            Sequence[File]: List of matching File DB objects.
        """
        # TODO: Add pagination container

        conditions = [File.type == file_type]

        if not include_deleted:
            conditions.append(File.deleted == False)  # noqa: E712

        if project_id is not None:
            conditions.append(File.project_id == project_id)

        if path:
            conditions.append(File.bucket_path.contains(path))

        if name:
            conditions.append(File.filename.ilike(f"%{name}%"))

        query = (
            select(File)
            .where(and_(*conditions))
            .order_by(File.created_at.desc(), File.id.desc())
        )

        if page_size:
            offset = (page - 1) * page_size
            query = query.offset(offset).limit(page_size)

        result = await self.db.execute(query)
        db_files = result.scalars().all()

        return db_files

    async def update_file(
        self,
        file_id: UUID,
        update_data: FileUpdateRequest,
    ) -> File | None:
        """
        Update metadata for an existing file.

        Args:
            file_id (UUID): UUID of the file to update.
            update_data (FileUpdateRequest): Data for updating the file.

        Returns:
            File | None: The updated File DB object if found, otherwise None.
        """
        file = await self.get_file(file_id=file_id)
        if not file:
            return None

        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(file, field, value)
        await self.db.commit()
        await self.db.refresh(file)
        logger.info(
            action=EventAction.CHANGE,
            outcome=EventOutcome.SUCCESS,
            category=EventCategory.FILE,
            file_id=str(file_id),
            file_path=file.bucket_path,
            message="Successfully updated file.",
        )
        return file

    async def delete_file(self, file_id: UUID, soft: bool = True) -> File:
        """
        Delete a file by marking it as deleted.

        Args:
            file_id (UUID): UUID of the file to delete.
            soft (bool): If True, files will be soft-deleted. If False, all file
                versions will be deleted including DS objects.

        Returns:
            File: The deleted File DB object if it existed.
        """
        # If hard delete, also include soft deleted
        file = await self.get_file(file_id=file_id, include_deleted=(not soft))
        if not file:
            raise FileNotFoundError(f"File {file_id} not found.")

        if not soft:
            await self.db.execute(delete(File).where(File.id == file_id))
            await self.db.commit()
            try:
                await self.storage_provider_service.delete_document(
                    document_name=file.bucket_path
                )
            except FileNotFoundError:
                logger.warn(
                    action=EventAction.DELETE,
                    outcome=EventOutcome.FAILURE,
                    category=EventCategory.FILE,
                    file_id=str(file_id),
                    file_path=file.bucket_path,
                    message="S3 file not found during delete.",
                )

            logger.info(
                action=EventAction.DELETE,
                outcome=EventOutcome.SUCCESS,
                category=EventCategory.FILE,
                file_id=str(file_id),
                file_path=file.bucket_path,
                message="Successfully hard deleted file.",
            )
        else:
            file.deleted = True
            await self.db.commit()
            await self.db.refresh(file)

            logger.info(
                action=EventAction.DELETE,
                outcome=EventOutcome.SUCCESS,
                category=EventCategory.FILE,
                file_id=str(file_id),
                file_path=file.bucket_path,
                message="Successfully soft deleted file.",
            )

        return file

    async def generate_download_url(
        self,
        file_id: UUID,
        inline: bool = False,
        include_deleted: bool = False,
        expiration_minutes: int = 5,
    ) -> tuple[File, str]:
        """
        Generate a signed URL to download a file from object storage.

        Args:
            file_id (UUID): The unique identifier of the file.
            inline (bool): If True, the file will be displayed inline in the browser.
            include_deleted (bool): If True, allows to download soft deleted files
            expiration_minutes (int): The expiration time in minutes
                for the download URL.

        Returns:
            tuple[File, str]: Returns a tuple containing
            the File object and the signed URL

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        file = await self.get_file(
            file_id=file_id,
            include_deleted=include_deleted,
        )
        if not file:
            logger.error(
                action=EventAction.DOWNLOAD,
                outcome=EventOutcome.FAILURE,
                category=EventCategory.FILE,
                default_event=LogEventDefault.DOCUMENT_DOWNLOAD,
                file_id=str(file_id),
                message="Failed to generate signed URL. File does not exist.",
            )
            raise FileNotFoundError(f"File '{file_id}' not found.")

        try:
            url = await self.storage_provider_service.generate_download_signed_url(
                document_name=file.bucket_path,
                mime_type=file.mime_type,
                inline=inline,
                expiration_minutes=expiration_minutes,
            )
            logger.info(
                action=EventAction.DOWNLOAD,
                outcome=EventOutcome.SUCCESS,
                category=EventCategory.FILE,
                default_event=LogEventDefault.DOCUMENT_DOWNLOAD,
                file_id=str(file_id),
                file_path=file.bucket_path,
                message="Generated signed download URL.",
            )
        except FileNotFoundError:
            logger.error(
                action=EventAction.DOWNLOAD,
                outcome=EventOutcome.FAILURE,
                category=EventCategory.FILE,
                default_event=LogEventDefault.DOCUMENT_DOWNLOAD,
                file_id=str(file_id),
                file_path=file.bucket_path,
                message="Failed to generate signed URL. Bucket path does not exist.",
            )
            raise

        return file, url

    async def generate_upload_url(self, file_data: UploadRequest) -> tuple[str, str]:
        """
        Generate a signed URL to upload a file to object storage.

        Args:
            file_data (UploadRequest): The metadata of the file to upload.

        Returns:
            tuple[str, str]: A signed URL and MIME type.
        """
        if file_data.type in (FileTypeEnum.DOCUMENT, FileTypeEnum.ZIP):
            await self._ensure_no_active_workflow(project_id=file_data.project_id)

        mime_type = validate_file_upload(
            filename=file_data.filename,
            allowed_extensions=settings.ALLOWED_FILE_EXTENSIONS,
            allowed_mime_types=settings.ALLOWED_FILE_TYPES,
        )

        _, version = await self._prepare_version_and_check_conflict(file_data=file_data)

        bucket_path = self._get_object_path(
            filename=file_data.filename,
            context=file_data,
            version=version,
        )
        try:
            url = await self.storage_provider_service.generate_upload_signed_url(
                document_name=bucket_path,
                mime_type=mime_type,
            )
            logger.info(
                action=EventAction.UPLOAD,
                outcome=EventOutcome.SUCCESS,
                category=EventCategory.FILE,
                default_event=LogEventDefault.DOCUMENT_UPLOAD,
                file_path=bucket_path,
                file_name=file_data.filename,
                message=f"Generated signed upload URL (version {version}).",
            )
        except Exception as e:
            logger.error(
                action=EventAction.UPLOAD,
                outcome=EventOutcome.FAILURE,
                category=EventCategory.FILE,
                default_event=LogEventDefault.DOCUMENT_UPLOAD,
                file_path=bucket_path,
                file_name=file_data.filename,
                message=(
                    f"Failed to generate signed upload URL "
                    f"(attempted version {version}): {e}"
                ),
            )
            raise

        return url, mime_type

    async def clean_up(
        self,
        retention_days: int,
        file_type: FileTypeEnum,
    ) -> Sequence[str]:
        """
        Deletes all files older than `retention_days` days of a given type.

        Args:
            retention_days (int): The number of days to delete.
            file_type (FileTypeEnum): The type of file to delete.

        Returns:
            Sequence(str): The list of file ids deleted.
        """
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)

        result = await self.db.execute(
            delete(File)
            .where(File.type == file_type)
            .where(File.created_at < cutoff)
            .returning(File.id, File.bucket_path)
        )

        deleted_rows = result.fetchall()
        if not deleted_rows:
            logger.debug(
                action=EventAction.DELETE,
                outcome=EventOutcome.SUCCESS,
                category=EventCategory.FILE,
                message=(
                    f"No {file_type.value} files older "
                    f"than {retention_days} days to delete."
                ),
            )
            return []

        deleted_ids = [str(row.id) for row in deleted_rows]
        bucket_paths = [row.bucket_path for row in deleted_rows if row.bucket_path]

        logger.info(
            action=EventAction.DELETE,
            outcome=EventOutcome.SUCCESS,
            category=EventCategory.FILE,
            message=(
                f"Deleting {len(deleted_ids)} old "
                f"{file_type.value} files from database."
            ),
        )
        await self.db.commit()

        for path in bucket_paths:
            try:
                await self.storage_provider_service.delete_document(document_name=path)
            except FileNotFoundError:
                logger.warn(
                    action=EventAction.DELETE,
                    outcome=EventOutcome.FAILURE,
                    category=EventCategory.FILE,
                    file_path=path,
                    message="Object already deleted from storage.",
                )
            except Exception as e:
                logger.error(
                    action=EventAction.DELETE,
                    outcome=EventOutcome.FAILURE,
                    category=EventCategory.FILE,
                    file_path=path,
                    message=f"Failed to delete object from storage: {e}",
                )
                raise

        return deleted_ids

    async def _ensure_no_active_workflow(
        self,
        project_id: UUID,
        blocking_states: dict[WorkflowStatusEnum, type[Exception]] | None = None,
    ) -> None:
        """
        Checks if a file is currently being processed.
        If yes an error is raised according to the status.

        Args:
            project_id (UUID): The ID of the project.
            blocking_states (dict[str, Exception | None]): Optional blocking states.
        """
        if not blocking_states:
            blocking_states = {
                WorkflowStatusEnum.REQUIRES_APPROVAL: WorkflowRequiresApprovalError,
                WorkflowStatusEnum.RUNNING: WorkflowInRunningStateError,
            }

        statuses = (
            (
                await self.db.execute(
                    select(ZipFile.workflow_status).where(
                        ZipFile.project_id == project_id
                    )
                )
            )
            .scalars()
            .all()
        )

        for status in set(statuses):
            if exception_cls := blocking_states.get(status):
                raise exception_cls(
                    f"Cannot upload a file or start new ZIP processing "
                    f"for project {project_id}: "
                    f"existing workflow is in state {status.value}."
                )

    async def start_file_processing(
        self,
        payload: StartFileProcessingRequest,
    ) -> StartFileProcessingResponse:
        """
        Start a Temporal file processing workflow for the given upload request.

        Args:
            payload (StartFileProcessingRequest): The upload request.

        Returns:
            StartFileProcessingResponse: The response from the workflow.
        """
        from src.services.workflows.workflow_models import FileProcessingInput
        from src.utils.service_utils import create_zip_file_service

        zip_file_service = await create_zip_file_service(db=self.db)
        await self._ensure_no_active_workflow(project_id=payload.project_id)

        zip_file = await zip_file_service.get_zip_file(zip_file_id=payload.file_id)
        if zip_file is None:
            raise FileNotFoundError("Uploaded zip file not found in storage.")
        current_status = zip_file.workflow_status

        # Directly set RUNNING status because of race condition
        await zip_file_service.update_zip_workflow_status(
            zip_file_id=payload.file_id,
            status=WorkflowStatusEnum.RUNNING,
        )

        workflow_input = FileProcessingInput(
            file_id=str(payload.file_id),
            filename=zip_file.filename,
            project_id=str(payload.project_id),
            file_type="ZIP",
            zip_path=zip_file.bucket_path,
        )

        try:
            handle = await self.temporal_workflow_service.run_workflow(
                workflow=WorkflowEnum.FILE_PROCESSING,
                workflow_input=workflow_input,
                workflow_id=str(payload.file_id),
            )
            description = await handle.describe()

            resolved_status = WorkflowStatusEnum(description.status.name)
        except Exception as e:
            await zip_file_service.update_zip_workflow_status(
                zip_file_id=payload.file_id,
                status=current_status,
            )
            logger.error(
                action=EventAction.NOTIFY,
                outcome=EventOutcome.FAILURE,
                category=EventCategory.FILE,
                message=f"Failed to start workflow for file {payload.file_id}: {e}",
            )
            raise

        return StartFileProcessingResponse(
            workflow_id=handle.id,
            run_id=description.run_id,
            workflow_status=resolved_status,
        )
