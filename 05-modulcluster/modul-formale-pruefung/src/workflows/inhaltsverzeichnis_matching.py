"""Orchestration workflow for Table of Contents (TOC) based document matching.

This module defines the `InhaltsverzeichnisMatchingWorkflow`, a high-level parent
workflow that coordinates the end-to-end process of TOC extraction and subsequent
document matching.
"""

from datetime import timedelta

from temporal.workflows.formale_pruefung import (
    DMSFileResponse,
    InhaltsverzeichnisFinderOutput,
    InhaltsverzeichnisFinderParams,
    InhaltsverzeichnisMatchingOutput,
    InhaltsverzeichnisMatchingParams,
    LLMMatchingOutput,
    LLMMatchingParams,
)
from temporal.workflows.formale_pruefung.inhaltsverzeichnis_matching import (
    INHALTSVERZEICHNIS_MATCHING_WORKFLOW_ID,
)
from temporalio import workflow
from temporalio.common import RetryPolicy

from src.activities.dms_activities import (
    DownloadJsonFromDmsInput,
    download_json_from_dms,
    upload_temporal_checkpoint,
)
from src.config.config import config
from src.schemas.dms_schemas import UploadTemporalCheckpointInput
from src.workflows.inhaltsverzeichnis_finder import InhaltsverzeichnisFinderWorkflow
from src.workflows.llm_matching import LLMMatchingWorkflow


@workflow.defn(name=INHALTSVERZEICHNIS_MATCHING_WORKFLOW_ID)
class InhaltsverzeichnisMatchingWorkflow:
    """Orchestrator workflow that chains TOC extraction and LLM-based matching."""

    @workflow.run
    async def run(self, params: InhaltsverzeichnisMatchingParams) -> DMSFileResponse:
        """Executes the TOC matching pipeline.

        Args:
            params (InhaltsverzeichnisMatchingParams): Configuration parameters.

        Returns:
            DMSFileResponse: The response from the final DMS upload.
        """
        workflow.logger.info(f"Starting InhaltsverzeichnisMatchingWorkflow for project {params.project_id}")

        # 1. Execute Finder Workflow
        finder_workflow_id = f"iv-finder-{params.project_id}-{workflow.info().run_id}"
        extraction_output: InhaltsverzeichnisFinderOutput = await workflow.execute_child_workflow(
            InhaltsverzeichnisFinderWorkflow.run,
            InhaltsverzeichnisFinderParams(project_id=params.project_id, document_types=params.document_types),
            id=finder_workflow_id,
        )

        # 2. Check Extraction Status & Early Return
        if extraction_output.status != "success":
            workflow.logger.warning("No Inhaltsverzeichnis found. Skipping matching.")

            failed_result = InhaltsverzeichnisMatchingOutput(
                inhaltsverzeichnis_extraction_output=extraction_output,
                inhaltsverzeichnis_matching_output=LLMMatchingOutput(
                    matched_document_types=[], unassigned_documents=[]
                ),
            )
            return await self._upload_result(failed_result, params)

        # 3. Prepare Matching Data
        document_types = extraction_output.document_types or []
        document_types_payload = [dt.model_dump() for dt in document_types]
        workflow.logger.info(f"Found {len(document_types)} document types. Starting matching.")

        # 4. Execute Matching Workflow
        matching_workflow_id = f"iv-matching-{params.project_id}-{workflow.info().run_id}"
        dms_response: DMSFileResponse = await workflow.execute_child_workflow(
            LLMMatchingWorkflow.run,
            LLMMatchingParams(
                project_id=params.project_id,
                document_types=document_types_payload,
            ),
            id=matching_workflow_id,
        )

        # 5. Download Matching Result JSON
        downloaded_data = await workflow.execute_activity(
            download_json_from_dms,
            DownloadJsonFromDmsInput(file_id=dms_response.id),
            start_to_close_timeout=timedelta(seconds=config.TEMPORAL.ACTIVITY_TIMEOUT_SECONDS),
            retry_policy=RetryPolicy(maximum_attempts=config.TEMPORAL.ACTIVITY_MAX_RETRIES),
        )

        # 6. Upload Final Composite Result
        final_result = InhaltsverzeichnisMatchingOutput(
            inhaltsverzeichnis_extraction_output=extraction_output,
            inhaltsverzeichnis_matching_output=LLMMatchingOutput(**downloaded_data),
        )

        return await self._upload_result(final_result, params)

    async def _upload_result(
        self,
        output_data: InhaltsverzeichnisMatchingOutput,
        params: InhaltsverzeichnisMatchingParams,
    ) -> DMSFileResponse:
        """Helper to upload the workflow result to the DMS.

        Args:
            output_data: The composite result object to upload.
            params: Workflow parameters containing configuration for retries/timeouts.

        Returns:
            DMSFileResponse: The upload confirmation metadata.
        """
        info = workflow.info()
        return await workflow.execute_activity(
            upload_temporal_checkpoint,
            UploadTemporalCheckpointInput(
                project_id=params.project_id,
                workflow_id=info.workflow_id,
                run_id=info.run_id,
                filename="result.json",
                payload=output_data.model_dump(mode="json"),
            ),
            start_to_close_timeout=timedelta(seconds=config.TEMPORAL.UPLOAD_ACTIVITY_TIMEOUT_SECONDS),
            retry_policy=RetryPolicy(maximum_attempts=config.TEMPORAL.ACTIVITY_MAX_RETRIES),
        )
