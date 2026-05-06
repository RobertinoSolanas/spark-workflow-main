# src/workflows/process_documents_workflow.py
"""
Temporal workflow for the main document processing pipeline.

This workflow processes documents from DMS (Document Management Service).
Input: List of file_ids and project_id
Output: Summary with processed file information
"""

import asyncio
import unicodedata
from collections.abc import Coroutine, Sequence
from datetime import timedelta
from pathlib import Path
from typing import Any

from temporal.workflows.inhaltsextraktion.types import (
    PROCESS_DOCUMENTS_WORKFLOW_ID,
    BaseMetadata,
    ProcessDocumentsWorkflowInput,
    ProcessDocumentsWorkflowOutput,
)
from temporalio import workflow
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import ApplicationError

from src.activities.dms_activities import (
    DmsFileInfo,
    dms_get_file_metadata,
    resolve_priority_file,
)
from src.activities.postprocessing import (
    CreateSummaryFromResultsInput,
    create_summary_from_results,
)
from src.config import snapshot_config
from src.env import ENV
from src.utils.sliding_window import sliding_window
from src.workflows.pageindex_structure.workflow import (
    PageindexStructureWorkflow,
    PageindexStructureWorkflowInput,
    PageindexStructureWorkflowOutput,
)
from src.workflows.qdrant.workflow import (
    QdrantBuilderWorkflow,
    QdrantBuilderWorkflowInput,
    QdrantBuilderWorkflowOutput,
)
from src.workflows.single_document_workflow import (
    SingleDocumentWorkflow,
    SingleDocumentWorkflowInput,
)
from src.workflows.types import SingleDocumentWorkflowOutput


def has_keyword_match(keywords: Sequence[str], file_info: DmsFileInfo) -> bool:
    normalized_name = unicodedata.normalize("NFC", file_info.filename.lower())
    normalized_keywords = [unicodedata.normalize("NFC", keyword.lower()) for keyword in keywords]
    if any(keyword in normalized_name for keyword in normalized_keywords):
        return True
    # Fallback: ASCII-only matching to handle mojibake/encoding corruption.
    # Filename: strip non-ASCII directly (mojibake chars are garbage).
    # Keywords: NFD first to decompose e.g. ä → a + combining diaeresis,
    # then strip non-ASCII to keep the base letter.
    ascii_name = normalized_name.encode("ascii", "ignore").decode()
    ascii_keywords = [unicodedata.normalize("NFD", k).encode("ascii", "ignore").decode() for k in normalized_keywords]
    return any(keyword in ascii_name for keyword in ascii_keywords if keyword)


@workflow.defn(name=PROCESS_DOCUMENTS_WORKFLOW_ID)
class ProcessDocumentsWorkflow:
    """
    Processes a list of documents from DMS. For each document, the
    SingleDocumentWorkflow is called. Finds priority documents like
    "Erläuterungsbericht" for base metadata extraction.
    """

    @workflow.run
    async def run(  # noqa: C901
        self, input: ProcessDocumentsWorkflowInput
    ) -> ProcessDocumentsWorkflowOutput:
        """
        Processes a list of documents from DMS, handling priority documents
        and creating a summary file.
        """
        cfg = snapshot_config()
        workflow_start_time = workflow.now()

        # Fetch metadata for all files
        file_infos: list[DmsFileInfo] = await asyncio.gather(
            *[dms_get_file_metadata(file_id) for file_id in input.file_ids]
        )
        max_concurrency = max(1, ENV.SINGLE_DOCUMENT_WORKFLOW_CONCURRENCY)

        processable_files: list[DmsFileInfo] = []
        priority_candidates: list[DmsFileInfo] = []
        for file_info in file_infos:
            if cfg.SKIP_DOCUMENTS_BY_KEYWORDS and has_keyword_match(cfg.SKIPPED_DOCUMENT_KEYWORDS, file_info):
                workflow.logger.info(f"Skipping file: {file_info.filename}")
                continue
            suffix = Path(file_info.filename).suffix.lower()
            if suffix not in cfg.ALLOWED_EXTENSIONS:
                continue
            if has_keyword_match(cfg.METADATA_PRIORITY_KEYWORDS, file_info):
                priority_candidates.append(file_info)
                continue
            processable_files.append(file_info)

        priority_file: DmsFileInfo | None = None
        if len(priority_candidates) == 1:
            priority_file = priority_candidates[0]
        elif len(priority_candidates) > 1:
            workflow.logger.warning(
                f"Found {len(priority_candidates)} priority candidates: "
                f"{[c.filename for c in priority_candidates]}. "
                "Resolving by file size."
            )
            try:
                priority_file = await resolve_priority_file(priority_candidates)
                # Add non-selected candidates back to regular processing
                for candidate in priority_candidates:
                    if candidate.file_id != priority_file.file_id:
                        processable_files.append(candidate)
            except Exception as e:
                workflow.logger.error(
                    f"Failed to resolve priority file: {e}. Adding all candidates back to regular processing."
                )
                processable_files.extend(priority_candidates)

        async def _execute_single_doc(
            file_info: DmsFileInfo,
            *,
            is_priority_doc: bool,
            base_metadata: BaseMetadata | None,
        ) -> SingleDocumentWorkflowOutput:
            """Execute a single document child workflow. Raises on failure."""
            child_input = SingleDocumentWorkflowInput(
                project_id=input.project_id,
                file_info=file_info,
                base_metadata=base_metadata,
                is_priority_doc=is_priority_doc,
            )
            # TODO: Check if a workflow with that ID already exists and if so, just return its result
            # For now we will just terminate existing ones for easier restarts
            return await workflow.execute_child_workflow(
                SingleDocumentWorkflow.run,
                child_input,
                # TODO: Not safe with time based UUIDs
                id=f"single-doc-{file_info.file_id[:8]}-{workflow.info().workflow_id[:8]}",
                id_reuse_policy=WorkflowIDReusePolicy.TERMINATE_IF_RUNNING,
                task_timeout=timedelta(seconds=60),
            )

        results: list[SingleDocumentWorkflowOutput] = []
        base_metadata = None

        # Run priority document first and get base_metadata from it
        # TODO: Ask about a literal category for the user to specify the priority document
        failed_priority: DmsFileInfo | None = None
        if priority_file:
            try:
                priority_result = await _execute_single_doc(
                    priority_file, is_priority_doc=True, base_metadata=base_metadata
                )
                results.append(priority_result)
                base_metadata = priority_result.base_metadata
            except Exception as e:
                workflow.logger.warning(f"Priority document failed: {e}. Will retry later.")
                failed_priority = priority_file

        # Build the runner closure for the sliding window
        async def process_one(file_info: DmsFileInfo) -> SingleDocumentWorkflowOutput:
            return await _execute_single_doc(file_info, is_priority_doc=False, base_metadata=base_metadata)

        ok, failed = await sliding_window(processable_files, process_one, max_concurrency)
        results.extend(ok)
        if failed_priority is not None:
            failed.append(failed_priority)

        # --- Retry loop for failed documents ---
        total_docs = len(processable_files) + (1 if priority_file else 0)
        max_allowed = max(
            round(total_docs * cfg.DOCUMENT_FAILURE_RATE_THRESHOLD),
            cfg.DOCUMENT_FAILURE_MIN_ALLOWED,
        )
        retry_round = 0
        while failed and retry_round < cfg.DOCUMENT_RETRY_MAX_ATTEMPTS:
            retry_round += 1
            prev_failed_count = len(failed)

            # Separate priority doc from regular docs for correct ordering
            retry_priority = None
            retry_others: list[DmsFileInfo] = []
            for fi in failed:
                if priority_file and fi.file_id == priority_file.file_id:
                    retry_priority = fi
                else:
                    retry_others.append(fi)

            workflow.logger.info(
                f"Retry round {retry_round}/{cfg.DOCUMENT_RETRY_MAX_ATTEMPTS}: "
                f"retrying {prev_failed_count} failed document(s) "
                f"(threshold: {max_allowed})"
            )

            # Exponential backoff, capped at 5 minutes
            delay = cfg.DOCUMENT_RETRY_DELAY_SECONDS * (2 ** (retry_round - 1))
            delay = min(delay, 300)
            await workflow.sleep(timedelta(seconds=delay))

            # Retry priority doc first (alone) so base_metadata is available
            if retry_priority:
                try:
                    priority_result = await _execute_single_doc(
                        retry_priority,
                        is_priority_doc=True,
                        base_metadata=base_metadata,
                    )
                    results.append(priority_result)
                    base_metadata = priority_result.base_metadata
                    retry_priority = None  # no longer failed
                except Exception as e:
                    workflow.logger.warning(f"Priority document retry round {retry_round} failed: {e}")

            # Retry one document at a time — failed documents likely exhausted
            # docling-serve resources (OOM), so parallel retry would repeat the
            # same overload pattern.
            ok2, retry_others_failed = await sliding_window(retry_others, process_one, 1)
            results.extend(ok2)

            # Rebuild failed list
            failed = retry_others_failed
            if retry_priority is not None:
                failed.append(retry_priority)

            # Circuit-breaker: abort if zero progress
            if len(failed) >= prev_failed_count:
                workflow.logger.error(
                    f"Retry round {retry_round}: no progress ({len(failed)} still failing). "
                    f"Likely systemic outage — aborting retries."
                )
                break

        # Final threshold check — fail workflow if too many documents still failing
        if len(failed) > max_allowed:
            raise ApplicationError(
                f"{len(failed)} document(s) failed after "
                f"{retry_round} retry round(s), exceeding threshold of "
                f"{max_allowed}: {[fi.filename for fi in failed]}",
                type="TooManyDocumentsFailed",
                non_retryable=True,
            )

        # Finalization
        if failed:
            workflow.logger.warning(
                f"{len(failed)} document(s) failed and were skipped: {[fi.filename for fi in failed]}"
            )
        workflow.logger.info(f"{len(results)} of {total_docs} documents processed successfully. Creating summary file.")

        # Calculate total workflow duration
        workflow_end_time = workflow.now()
        total_duration_seconds = (workflow_end_time - workflow_start_time).total_seconds()

        # Create summary using DMS
        summary_result = await create_summary_from_results(
            CreateSummaryFromResultsInput(
                results=results,
                project_id=input.project_id,
                base_metadata=base_metadata,
                total_duration_seconds=total_duration_seconds,
            ),
        )

        # --- Post-extraction: Qdrant + PageIndex in parallel (failure-isolated) ---
        wf_id = workflow.info().workflow_id
        qdrant_result: QdrantBuilderWorkflowOutput | None = None
        pageindex_result: PageindexStructureWorkflowOutput | None = None

        async def _run_qdrant() -> QdrantBuilderWorkflowOutput | None:
            try:
                return await workflow.execute_child_workflow(
                    QdrantBuilderWorkflow.run,
                    QdrantBuilderWorkflowInput(project_id=str(input.project_id)),
                    id=f"qdrant-{wf_id[:8]}",
                    id_reuse_policy=WorkflowIDReusePolicy.TERMINATE_IF_RUNNING,
                    task_timeout=timedelta(seconds=60),
                )
            except Exception as e:
                workflow.logger.error(f"Qdrant child workflow failed: {e}")
                return None

        async def _run_pageindex() -> PageindexStructureWorkflowOutput | None:
            try:
                return await workflow.execute_child_workflow(
                    PageindexStructureWorkflow.run,
                    PageindexStructureWorkflowInput(project_id=input.project_id),
                    id=f"pageindex-{wf_id[:8]}",
                    id_reuse_policy=WorkflowIDReusePolicy.TERMINATE_IF_RUNNING,
                    task_timeout=timedelta(seconds=60),
                )
            except Exception as e:
                workflow.logger.error(f"PageIndex child workflow failed: {e}")
                return None

        post_tasks: list[Coroutine[Any, Any, Any]] = []
        if not input.skip_qdrant:
            post_tasks.append(_run_qdrant())
        if not input.skip_pageindex:
            post_tasks.append(_run_pageindex())

        if post_tasks:
            post_results = await asyncio.gather(*post_tasks)
            idx = 0
            if not input.skip_qdrant:
                result = post_results[idx]
                if isinstance(result, QdrantBuilderWorkflowOutput):
                    qdrant_result = result
                idx += 1
            if not input.skip_pageindex:
                result = post_results[idx]
                if isinstance(result, PageindexStructureWorkflowOutput):
                    pageindex_result = result

        return ProcessDocumentsWorkflowOutput(
            summary_file_id=summary_result.summary_file_id,
            summary_data=summary_result.summary_data,
            processed_file_ids=[result.final_json_file_id for result in results],
            qdrant_ok=qdrant_result is not None,
            qdrant_processed_ids=qdrant_result.processed_document_ids if qdrant_result else [],
            qdrant_failed_ids=qdrant_result.failed_document_ids if qdrant_result else [],
            pageindex_ok=pageindex_result is not None,
            pageindex_created_files=len(pageindex_result.created_files) if pageindex_result else 0,
        )
