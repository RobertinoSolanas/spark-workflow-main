import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

from src.config.settings import settings
from src.models.db.workflow_enum import (
    ActionEnum,
    ApprovalStatus,
    ErrorCode,
    WorkflowStatusEnum,
)
from src.services.workflows.activities import validate_zip
from src.services.workflows.activities.activity_models import ValidateZipInput
from src.services.workflows.activities.delete_file import DeleteFileInput, delete_file
from src.services.workflows.activities.rename_file import RenameFileInput, rename_file
from src.services.workflows.workflow_models import (
    FileProcessingFailure,
    FileProcessingInput,
    FileProcessingOutput,
    FileProcessingSuccess,
    FileProcessingSummary,
)

with workflow.unsafe.imports_passed_through():
    from src.services.workflows.activities.compute_sha_diff import (
        ComputeShaDiffInput,
        DeleteChange,
        FileChange,
        FileDiffResult,
        NewFile,
        RenameChange,
        create_sha256_diff,
    )
    from src.services.workflows.activities.extract_zip import (
        ExtractZipInput,
        extract_zip,
    )
    from src.services.workflows.activities.ingest_file import (
        IngestFileInput,
        SingleFileResult,
        ingest_file,
    )
    from src.services.workflows.activities.update_workflow_status import (
        UpdateFileStatusInput,
        update_file_status,
    )


ZIP_PROCESSING_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=10),
    maximum_interval=timedelta(minutes=1),
    maximum_attempts=50,
)


@workflow.defn()
class FileProcessingWorkflow:
    def __init__(self) -> None:
        self.approved: bool | None = None
        self._diff_result: FileDiffResult | None = None

    @workflow.query
    def get_diff_summary(self) -> FileDiffResult | None:
        """Returns the diff that the user should review."""

        return self._diff_result

    @workflow.signal
    def set_diff_summary(self, diff: FileDiffResult) -> None:
        """Allows the user to modify the diff."""
        self._diff_result = diff

    @workflow.query
    def get_approval_status(self) -> str:
        """Returns the approval status of the workflow."""
        if self.approved is None:
            return ApprovalStatus.PENDING
        return ApprovalStatus.APPROVED if self.approved else ApprovalStatus.REJECTED

    @workflow.signal
    async def approve_upload(self) -> None:
        """Signal to approve the upload."""
        self.approved = True

    @workflow.signal
    async def reject_upload(self) -> None:
        """Signal to reject the upload."""
        self.approved = False

    @workflow.run
    async def run(self, workflow_input: FileProcessingInput) -> FileProcessingOutput:
        workflow.logger.info(
            f"FileProcessingWorkflow started for '{workflow_input.filename}' "
            f"(project={workflow_input.project_id}, type={workflow_input.file_type})"
        )
        self.approved = None

        # Note: Temporal termination is a hard stop. The workflow code does not
        # get a final callback, so TERMINATED must be set by the caller that
        # invokes WorkflowHandle.terminate(...).
        await self._set_zip_status(
            zip_file_id=workflow_input.file_id,
            status=WorkflowStatusEnum.RUNNING,
        )

        try:
            # Extract ZIP file
            extract_zip_results = await self._validate_and_extract_zip(
                workflow_input=workflow_input
            )

            failed_extraction_files = [
                file for file in extract_zip_results if not file.success
            ]
            success_extraction_files = [
                file for file in extract_zip_results if file.success
            ]
            workflow.logger.info(
                f"Extraction result: "
                f"Failed: {len(failed_extraction_files)}, "
                f"Success: {len(success_extraction_files)}"
            )

            # Create sha256 DIFF with successful files
            self._diff_result = await self._calculate_sha256_diff(
                activity_input=success_extraction_files,
                workflow_input=workflow_input,
            )

            # Handle the approval of uploads
            status = await self._handle_approval(workflow_input=workflow_input)
            if not status:
                return FileProcessingOutput(
                    successful=[],
                    failed=[],
                    summary=FileProcessingSummary(
                        total=0,
                        succeeded=0,
                        failed=0,
                    ),
                    status=ApprovalStatus.REJECTED,
                )

            # Ingest the files into DMS
            upload_results = await self._ingest_files(
                ingest_input=self._diff_result.new + self._diff_result.changed,
                workflow_input=workflow_input,
            )

            # Delete files from DMS
            delete_results = await self._delete_files(
                delete_input=self._diff_result.deleted,
                workflow_input=workflow_input,
            )

            # Rename files
            rename_results = await self._rename_files(
                rename_input=self._diff_result.renamed,
                workflow_input=workflow_input,
            )

            successful: list[FileProcessingSuccess] = []
            failed: list[FileProcessingFailure] = []
            for result in (
                upload_results
                + rename_results
                + delete_results
                + failed_extraction_files
            ):
                if result.success:
                    successful.append(
                        FileProcessingSuccess(
                            file_id=result.file_id,
                            filename=result.filename,
                            action=result.action,
                        )
                    )
                    continue

                failed.append(
                    FileProcessingFailure(
                        filename=result.filename,
                        action=result.action,
                        error_code=result.error_code,
                        error_message=result.error_message,
                    )
                )

            await self._set_zip_status(
                zip_file_id=workflow_input.file_id,
                status=WorkflowStatusEnum.COMPLETED,
            )

            return FileProcessingOutput(
                successful=successful,
                failed=failed,
                summary=FileProcessingSummary(
                    total=len(successful) + len(failed),
                    succeeded=len(successful),
                    failed=len(failed),
                ),
                status=ApprovalStatus.APPROVED,
            )
        except asyncio.CancelledError:
            try:
                await self._set_zip_status(
                    zip_file_id=workflow_input.file_id,
                    status=WorkflowStatusEnum.CANCELED,
                )
            except Exception as exc:
                workflow.logger.exception(
                    f"Failed to update zip workflow status to 'CANCELED'. "
                    f"Exception raised: {exc}"
                )
            raise
        except Exception:
            try:
                await self._set_zip_status(
                    zip_file_id=workflow_input.file_id,
                    status=WorkflowStatusEnum.FAILED,
                )
            except Exception as exc:
                workflow.logger.exception(
                    "Failed to update zip workflow status to 'FAILED'. "
                    f"Exception raised: {exc}"
                )
            raise

    async def _set_zip_status(
        self,
        zip_file_id: str,
        status: WorkflowStatusEnum,
    ) -> None:
        """Helper method to set a ZIP file status."""
        await workflow.execute_activity(
            update_file_status,
            UpdateFileStatusInput(
                zip_file_id=zip_file_id,
                status=status,
            ),
            start_to_close_timeout=timedelta(seconds=30),
        )

    async def _validate_and_extract_zip(
        self,
        workflow_input: FileProcessingInput,
    ) -> list[SingleFileResult]:
        """Validate and extract ZIP, then ingest contained files."""
        if not workflow_input.zip_path:
            return [
                SingleFileResult(
                    success=False,
                    filename=workflow_input.filename,
                    error_code=ErrorCode.ZIP_NOT_FOUND,
                    error_message="Zip file not found in storage",
                    action=ActionEnum.UNZIP,
                )
            ]

        await workflow.execute_activity(
            validate_zip,
            ValidateZipInput(
                zip_path=workflow_input.zip_path,
                filename=workflow_input.filename,
            ),
            start_to_close_timeout=timedelta(seconds=30),
        )

        return await workflow.execute_activity(
            extract_zip,
            ExtractZipInput(
                zip_file_id=workflow_input.file_id,
                filename=workflow_input.filename,
                project_id=workflow_input.project_id,
                zip_path=workflow_input.zip_path,
            ),
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=ZIP_PROCESSING_RETRY_POLICY,
        )

    async def _calculate_sha256_diff(
        self,
        activity_input: list[SingleFileResult],
        workflow_input: FileProcessingInput,
    ):
        """Helper method to calculate sha256 diff."""
        return await workflow.execute_activity(
            create_sha256_diff,
            ComputeShaDiffInput(
                project_id=workflow_input.project_id,
                zip_file_id=workflow_input.file_id,
                files=activity_input,
            ),
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=ZIP_PROCESSING_RETRY_POLICY,
        )

    async def _ingest_files(
        self,
        ingest_input: list[FileChange | NewFile],
        workflow_input: FileProcessingInput,
    ) -> list[SingleFileResult]:
        """Helper method to ingest files."""
        results: list[SingleFileResult] = []
        for file in ingest_input:
            file_result = await workflow.execute_activity(
                ingest_file,
                IngestFileInput(
                    project_id=workflow_input.project_id,
                    zip_file_id=workflow_input.file_id,
                    filename=file.filename,
                    bucket_path=file.bucket_path,
                ),
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=ZIP_PROCESSING_RETRY_POLICY,
            )
            results.append(file_result)
        return results

    async def _delete_files(
        self,
        delete_input: list[DeleteChange],
        workflow_input: FileProcessingInput,
    ) -> list[SingleFileResult]:
        """Helper method to delete files."""
        results: list[SingleFileResult] = []
        for file in delete_input:
            file_result = await workflow.execute_activity(
                delete_file,
                DeleteFileInput(
                    project_id=workflow_input.project_id,
                    filename=file.filename,
                    file_id=file.file_id,
                ),
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=ZIP_PROCESSING_RETRY_POLICY,
            )
            results.append(file_result)
        return results

    async def _rename_files(
        self,
        rename_input: list[RenameChange],
        workflow_input: FileProcessingInput,
    ) -> list[SingleFileResult]:
        """Helper method to rename files."""
        results: list[SingleFileResult] = []
        for file in rename_input:
            file_result = await workflow.execute_activity(
                rename_file,
                RenameFileInput(
                    project_id=workflow_input.project_id,
                    old_name=file.old_name,
                    new_name=file.new_name,
                    file_id=file.file_id,
                ),
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=ZIP_PROCESSING_RETRY_POLICY,
            )
            results.append(file_result)
        return results

    async def _handle_approval(
        self, workflow_input: FileProcessingInput
    ) -> bool | None:
        """Helper method to handle approval."""
        if settings.TEMPORAL.ENABLE_APPROVAL:
            # Set workflow status to requires human interaction
            await self._set_zip_status(
                zip_file_id=workflow_input.file_id,
                status=WorkflowStatusEnum.REQUIRES_APPROVAL,
            )
            try:
                await workflow.wait_condition(
                    lambda: self.approved is not None,
                    timeout=timedelta(days=settings.TEMPORAL.APPROVAL_TIMEOUT_DAYS),
                )
            except TimeoutError:
                workflow.logger.info("Timed out waiting for approval")
                self.approved = False
        else:
            self.approved = True

        # If not approved, terminate with reason REEJECTED
        if not self.approved:
            workflow.logger.info("File processing rejected")
            await self._set_zip_status(
                zip_file_id=workflow_input.file_id,
                status=WorkflowStatusEnum.COMPLETED,
            )
        return self.approved
