"""Defines Workflow"""

import re
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

from src.qdrant.schemas import ClaimPayload
from src.workflows.input_schemas import (
    OrchestratorInputSchema,
    SingleDocumentWorkflowInputSchema,
)

CLAIM_EXTRACTION_SINGLE_DOCUMENT_WORKFLOW_ID = "claim-extraction-single-document"
CLAIM_EXTRACTION_ORCHESTRATOR_WORKFLOW_ID = "claim-extraction-orchestrator"

with workflow.unsafe.imports_passed_through():
    from src.activities.dms_activities import (
        fetch_erlauterungsbericht_document_ids,
    )
    from src.activities.extraction_activities import (
        extract_claims_from_row_batch,
        extract_text_claims,
        parse_table_structure,
    )
    from src.activities.qdrant_activities import (
        delete_document_from_qdrant,
        embed_and_upload_claims,
        fetch_and_prepare_chunks,
        init_qdrant_collection,
    )
    from src.config.config import config
    from src.workflows.qdrant_wf.schemas.table_extraction import ParsedTable
    from src.workflows.qdrant_wf.schemas.workflow import (
        DocumentActivityInput,
        EmbedAndUploadInput,
        ExtractClaimsFromRowBatchInput,
        ExtractTextClaimsInput,
    )
    from src.workflows.utils import sliding_window


def _extract_table_content(content: str) -> str:
    if "<table_content>" in content:
        m = re.search(
            r"<table_content>\s*(.*?)\s*</table_content>",
            content,
            re.DOTALL | re.IGNORECASE,
        )
        if m:
            return m.group(1).strip()
    return content


@workflow.defn
class ClaimExtractionSingleDocumentWorkflow:
    """Child workflow that processes a single document: fetch chunks, extract claims, upload."""

    @workflow.run
    async def run(self, inp: SingleDocumentWorkflowInputSchema) -> None:
        # Phase 1: Delete existing document claims from Qdrant
        await workflow.execute_activity(
            delete_document_from_qdrant,
            arg=DocumentActivityInput(project_id=inp.project_id, document_id=inp.document_id),
            start_to_close_timeout=timedelta(seconds=config.TEMPORAL.ACTIVITY_TIMEOUT_SECONDS),
        )

        # Phase 2
        chunk_payloads = await workflow.execute_activity(
            fetch_and_prepare_chunks,
            arg=DocumentActivityInput(project_id=inp.project_id, document_id=inp.document_id),
            start_to_close_timeout=timedelta(seconds=config.TEMPORAL.ACTIVITY_TIMEOUT_SECONDS),
        )

        text_chunks = [c for c in chunk_payloads if c.chunk_type == "text"]
        table_chunks = [c for c in chunk_payloads if c.chunk_type == "table"]

        llm_queue = workflow.info().task_queue + config.LLM_TASK_QUEUE_SUFFIX

        # Phase 2: Extract text claims
        text_claims_list: list[list[ClaimPayload]] = await sliding_window(
            text_chunks,
            lambda chunk: workflow.execute_activity(
                extract_text_claims,
                ExtractTextClaimsInput(
                    project_id=inp.project_id,
                    document_id=inp.document_id,
                    erlauterungsbericht=inp.is_erlaeuterungsbericht,
                    chunk=chunk,
                ),
                task_queue=llm_queue,
                start_to_close_timeout=timedelta(seconds=config.TEMPORAL.LLM_ACTIVITY_TIMEOUT_SECONDS),
                retry_policy=config.TEMPORAL.LLM_RETRY_POLICY,
            ),
            concurrency=config.TEMPORAL.MAX_PENDING_ACTIVITIES,
        )

        # Flatten the list of lists and attach metadata
        text_claims = [text_claim for sublist in text_claims_list for text_claim in sublist]

        # Phase 3: Parse table structures
        parsed_tables: list[ParsedTable] = await sliding_window(
            table_chunks,
            lambda chunk: workflow.execute_activity(
                parse_table_structure,
                arg=chunk,
                task_queue=llm_queue,
                start_to_close_timeout=timedelta(seconds=config.TEMPORAL.LLM_ACTIVITY_TIMEOUT_SECONDS),
                retry_policy=config.TEMPORAL.LLM_RETRY_POLICY,
            ),
            concurrency=config.TEMPORAL.MAX_PENDING_ACTIVITIES,
        )

        # Split Tables with more than TABLE_ROW_BATCH_SIZE rows into multiple tables
        small_tables: list[ParsedTable] = []
        batch_size = config.QDRANT_BUILDER.TABLE_ROW_BATCH_SIZE
        for table in parsed_tables:
            if len(table.rows) > batch_size:
                row_batches = [table.rows[i : i + batch_size] for i in range(0, len(table.rows), batch_size)]
            else:
                row_batches = [table.rows]
            for row_batch in row_batches:
                small_tables.append(
                    ParsedTable(
                        chunk_id=table.chunk_id,
                        raw_content=table.raw_content,
                        header=table.header,
                        rows=row_batch,
                        title=table.title,
                    )
                )

        table_claims_list: list[list[ClaimPayload]] = await sliding_window(
            small_tables,
            lambda table: workflow.execute_activity(
                extract_claims_from_row_batch,
                ExtractClaimsFromRowBatchInput(
                    project_id=inp.project_id,
                    document_id=inp.document_id,
                    erlauterungsbericht=inp.is_erlaeuterungsbericht,
                    table=table,
                ),
                task_queue=llm_queue,
                start_to_close_timeout=timedelta(seconds=config.TEMPORAL.LLM_ACTIVITY_TIMEOUT_SECONDS),
                retry_policy=config.TEMPORAL.LLM_RETRY_POLICY,
            ),
            concurrency=config.TEMPORAL.MAX_PENDING_ACTIVITIES,
        )

        # Flatten the table claims list
        table_claims = [claim for sublist in table_claims_list for claim in sublist]

        all_claims = text_claims + table_claims

        batch_size = config.EMBEDDING.UPLOAD_BATCH_SIZE
        claim_batches = [all_claims[i : i + batch_size] for i in range(0, len(all_claims), batch_size)]

        await sliding_window(
            claim_batches,
            lambda batch: workflow.execute_activity(
                embed_and_upload_claims,
                arg=EmbedAndUploadInput(claims=batch),
                start_to_close_timeout=timedelta(seconds=config.TEMPORAL.UPLOAD_ACTIVITY_TIMEOUT_SECONDS),
            ),
            concurrency=config.TEMPORAL.MAX_PENDING_ACTIVITIES,
        )
        workflow.logger.info(f"Successfully processed document {inp.document_id}")


@workflow.defn
class ClaimExtractionOrchestratorWorkflow:
    """Orchestrates claim extraction and indexing across multiple documents."""

    @workflow.run
    async def run(self, inp: OrchestratorInputSchema) -> None:
        workflow.logger.info(f"Starting orchestration for {len(inp.document_ids)} documents.")

        await workflow.execute_activity(
            init_qdrant_collection,
            start_to_close_timeout=timedelta(seconds=config.TEMPORAL.ACTIVITY_TIMEOUT_SECONDS),
            retry_policy=RetryPolicy(maximum_attempts=config.QDRANT_BUILDER.DEFAULT_ACTIVITY_RETRIES),
        )

        erlauterungsbericht_ids = await workflow.execute_activity(  # type: ignore[no-matching-overload]
            fetch_erlauterungsbericht_document_ids,
            inp.classification_file_id,
            start_to_close_timeout=timedelta(seconds=config.TEMPORAL.ACTIVITY_TIMEOUT_SECONDS),
        )
        erlauterungsbericht_set = set(erlauterungsbericht_ids)
        workflow.logger.info(f"Found {len(erlauterungsbericht_ids)} Erläuterungsbericht documents.")

        child_futures = [
            workflow.execute_child_workflow(
                ClaimExtractionSingleDocumentWorkflow.run,
                arg=SingleDocumentWorkflowInputSchema(
                    project_id=inp.project_id,
                    document_id=doc_id,
                    is_erlaeuterungsbericht=doc_id in erlauterungsbericht_set,
                ),
                task_queue=workflow.info().task_queue,
                id=f"qdrant-worker-{inp.project_id}-{doc_id}",
            )
            for doc_id in inp.document_ids
        ]
        await workflow.asyncio.gather(*child_futures)
        workflow.logger.info("All document workers finished successfully.")
