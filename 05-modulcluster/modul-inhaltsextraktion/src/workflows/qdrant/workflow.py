"""QdrantBuilderWorkflow — indexes processed document chunks into Qdrant."""

from typing import Any
from uuid import uuid4

from pydantic import BaseModel
from temporalio import workflow
from temporalio.client import Client, WorkflowHandle
from temporalio.exceptions import ApplicationError

from src.activities.qdrant import (
    QdrantDocumentInput,
    QdrantExtractionFile,
    get_inhalts_extraktion_docs,
    index_document_to_qdrant,
    init_qdrant_collection,
)
from src.config import snapshot_config
from src.utils.sliding_window import sliding_window

build_qdrant_workflow_id = "build-qdrant-workflow"


class QdrantBuilderWorkflowInput(BaseModel):
    """Input parameters for QdrantBuilderWorkflow."""

    project_id: str


class QdrantBuilderWorkflowOutput(BaseModel):
    """Output with per-document success/failure tracking."""

    processed_document_ids: list[str]
    failed_document_ids: list[str]


async def start_qdrant_build(client: Client, input: QdrantBuilderWorkflowInput) -> WorkflowHandle[Any, Any]:
    from src.env import ENV

    return await client.start_workflow(
        build_qdrant_workflow_id,
        input,
        id=str(uuid4()),
        task_queue=ENV.TEMPORAL_TASK_QUEUE,
    )


async def execute_qdrant_build(client: Client, input: QdrantBuilderWorkflowInput) -> QdrantBuilderWorkflowOutput:
    from src.env import ENV

    return await client.execute_workflow(
        build_qdrant_workflow_id,
        input,
        id=str(uuid4()),
        task_queue=ENV.TEMPORAL_TASK_QUEUE,
    )


@workflow.defn(name=build_qdrant_workflow_id)
class QdrantBuilderWorkflow:
    """Workflow that builds a Qdrant vector index for a project.

    Lists all _processed.json extraction results from DMS, initialises the
    Qdrant collection (idempotent), and processes documents in sliding-window
    concurrency using activity wrappers with proper retry policies.
    """

    @workflow.run
    async def run(self, params: QdrantBuilderWorkflowInput) -> QdrantBuilderWorkflowOutput:
        cfg = snapshot_config()

        workflow.logger.info(
            "Starting Qdrant build for project %s.",
            params.project_id,
        )

        # 1. Initialise collection (idempotent — preserves existing data)
        await init_qdrant_collection()

        # 2. List all _processed.json extraction files from DMS
        extraction_files: list[QdrantExtractionFile] = await get_inhalts_extraktion_docs(params.project_id)

        if not extraction_files:
            raise ApplicationError(
                f"No _processed.json files found in DMS for project {params.project_id}.",
                type="QdrantNoDocumentsError",
                non_retryable=True,
            )

        workflow.logger.info("Found %d extraction files to index.", len(extraction_files))

        # 3. Process with sliding window concurrency
        async def _index_one(ef: QdrantExtractionFile) -> str:
            return await index_document_to_qdrant(
                QdrantDocumentInput(
                    extraction_file_id=ef.extraction_file_id,
                    project_id=ef.project_id,
                )
            )

        processed_document_ids, failed_files = await sliding_window(
            extraction_files, _index_one, cfg.QDRANT_PARALLEL_DOCS_SIZE
        )
        failed_document_ids = [ef.extraction_file_id for ef in failed_files]

        if not processed_document_ids:
            raise ApplicationError(
                f"All {len(failed_document_ids)} document uploads to Qdrant failed. Check activity logs for details.",
                type="QdrantAllUploadsFailedError",
                non_retryable=True,
            )

        workflow.logger.info(
            "Qdrant build complete: %d succeeded, %d failed.",
            len(processed_document_ids),
            len(failed_document_ids),
        )

        return QdrantBuilderWorkflowOutput(
            processed_document_ids=processed_document_ids,
            failed_document_ids=failed_document_ids,
        )
