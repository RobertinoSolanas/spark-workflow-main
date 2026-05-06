from datetime import timedelta

from temporalio import workflow

from src.config.config import config
from src.workflows.check_logic_wf.schemas.cluster_summarizer_schemas import (
    ClusteringInput,
    InconsistencyPair,
)
from src.workflows.check_logic_wf.schemas.context_checker_schemas import (
    ContextCheckerInput,
)
from src.workflows.check_logic_wf.schemas.output_schemas import (
    Contradiction,
    ContradictionStatus,
    DocumentOutput,
)
from src.workflows.check_logic_wf.schemas.risk_screener_schemas import (
    DocumentBundleRequest,
    DocumentBundleResult,
    ScreeningCandidateBundle,
)
from src.workflows.input_schemas import SingleDocumentWorkflowInputSchema

PLAUSIBILITY_CHECK_SINGLE_DOCUMENT_WORKFLOW_ID = "plausibility-check-single-document"

with workflow.unsafe.imports_passed_through():
    from src.activities.cluster_summarizer import build_clusters, summarize_cluster
    from src.activities.context_checker import check_conflict
    from src.activities.dms_activities import (
        UploadTemporalCheckpointInput,
        upload_temporal_checkpoint,
    )
    from src.activities.qdrant_activities import get_claim_ids
    from src.activities.risk_screener import build_screening_bundles_for_document, screen_claim_bundle
    from src.dms.schemas import DMSFileResponse
    from src.workflows.qdrant_wf.schemas.workflow import DocumentActivityInput
    from src.workflows.utils import sliding_window


def _deduplicate_bundles(
    bundles: list[ScreeningCandidateBundle],
) -> list[ScreeningCandidateBundle]:
    """Remove symmetric claim pairs, keeping only the direction whose primary claim
    appears first in ``bundles``.

    For every (A, B) pair discovered across all bundles, only the bundle whose
    primary claim is encountered first retains the reference.
    This is a pure deterministic function — safe to call directly in workflow code.
    """
    seen_pairs: set[frozenset[str]] = set()
    deduplicated: list[ScreeningCandidateBundle] = []

    for bundle in bundles:
        kept_refs: list[str] = []
        for ref_id in bundle.reference_claims:
            pair: frozenset[str] = frozenset({bundle.claim_id, ref_id})
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                kept_refs.append(ref_id)
        deduplicated.append(bundle.model_copy(update={"reference_claims": kept_refs}))

    return deduplicated


@workflow.defn
class PlausibilityCheckSingleDocumentWorkflow:
    """Runs the full plausibility-check pipeline for a single document."""

    @workflow.run
    async def run(self, workflow_input: SingleDocumentWorkflowInputSchema) -> DMSFileResponse:
        """Execute screening, contextual verification, clustering, summarization, and upload."""
        claim_ids: list[str] = await workflow.execute_activity(
            get_claim_ids,
            DocumentActivityInput(
                project_id=workflow_input.project_id,
                document_id=workflow_input.document_id,
            ),
            start_to_close_timeout=timedelta(seconds=config.TEMPORAL.ACTIVITY_TIMEOUT_SECONDS),
        )

        raw_bundle_result: DocumentBundleResult = await workflow.execute_activity(
            build_screening_bundles_for_document,
            DocumentBundleRequest(
                project_id=workflow_input.project_id,
                document_id=workflow_input.document_id,
                claim_ids=claim_ids,
            ),
            start_to_close_timeout=timedelta(seconds=config.TEMPORAL.ACTIVITY_TIMEOUT_SECONDS),
        )
        bundles = _deduplicate_bundles(raw_bundle_result.bundles)

        screening_results = await sliding_window(
            bundles,
            lambda bundle: workflow.execute_activity(
                screen_claim_bundle,
                bundle,
                task_queue=workflow.info().task_queue + config.LLM_TASK_QUEUE_SUFFIX,
                start_to_close_timeout=timedelta(seconds=config.TEMPORAL.LLM_ACTIVITY_TIMEOUT_SECONDS),
                retry_policy=config.TEMPORAL.LLM_RETRY_POLICY,
            ),
            concurrency=config.TEMPORAL.MAX_PENDING_ACTIVITIES,
        )

        context_check_activity_handles = [
            workflow.start_activity(
                check_conflict,
                ContextCheckerInput(
                    project_id=workflow_input.project_id,
                    document_id=workflow_input.document_id,
                    claim_id=hit.claim_id,
                    reference_claim_id=hit.reference_id,
                    screening_note=hit.note,
                ),
                task_queue=workflow.info().task_queue + config.LLM_TASK_QUEUE_SUFFIX,
                start_to_close_timeout=timedelta(seconds=config.TEMPORAL.LLM_ACTIVITY_TIMEOUT_SECONDS),
                retry_policy=config.TEMPORAL.LLM_RETRY_POLICY,
            )
            for screening_bundle_result in screening_results
            for hit in screening_bundle_result.hits
        ]

        context_check_outputs = await workflow.asyncio.gather(*context_check_activity_handles)

        inconsistency_pairs = []
        for result in context_check_outputs:
            if result.is_verified_inconsistency and result.updated_verdict is not None:
                inconsistency_pairs.append(
                    InconsistencyPair(
                        chunk_a_id=result.chunk_a_id,
                        chunk_b_id=result.chunk_b_id,
                        claim_a_id=result.claim_a_id,
                        claim_b_id=result.claim_b_id,
                        content_a_excerpt=result.updated_verdict.chunk_a_excerpt,
                        content_b_excerpt=result.updated_verdict.chunk_b_excerpt,
                        chunk_a_document_name=result.chunk_a_context.document_name,
                        chunk_b_document_name=result.chunk_b_context.document_name,
                        chunk_a_page_number=(
                            result.chunk_a_context.page_numbers[0] if result.chunk_a_context.page_numbers else None
                        ),
                        chunk_b_page_number=(
                            result.chunk_b_context.page_numbers[0] if result.chunk_b_context.page_numbers else None
                        ),
                        title=result.updated_verdict.title,
                        explanation=result.updated_verdict.explanation,
                    )
                )

        inconsistency_cluster_groups = await workflow.execute_activity(
            build_clusters,
            ClusteringInput(
                project_id=workflow_input.project_id,
                document_id=workflow_input.document_id,
                inconsistency_pairs=inconsistency_pairs,
            ),
            start_to_close_timeout=timedelta(seconds=config.TEMPORAL.ACTIVITY_TIMEOUT_SECONDS),
        )

        summarizer_activity_results = await sliding_window(
            inconsistency_cluster_groups.clusters,
            lambda cluster: workflow.execute_activity(
                summarize_cluster,
                cluster,
                start_to_close_timeout=timedelta(seconds=config.TEMPORAL.LLM_ACTIVITY_TIMEOUT_SECONDS),
                task_queue=workflow.info().task_queue + config.LLM_TASK_QUEUE_SUFFIX,
                retry_policy=config.TEMPORAL.LLM_RETRY_POLICY,
            ),
            concurrency=config.TEMPORAL.MAX_PENDING_ACTIVITIES,
        )
        # Flatten per-cluster summarizer responses into one list.
        inconsistency_summaries = [
            summary for result in summarizer_activity_results for summary in result.inconsistencies
        ]

        # Build the document-level output object stored in DMS.
        contradictions = []
        for summary in inconsistency_summaries:
            contradictions.append(
                Contradiction(
                    id=str(workflow.uuid4()),
                    title=summary.cluster_title,
                    description=summary.cluster_explanation,
                    status=ContradictionStatus.OPEN,
                    occurrences=summary.occurrences,
                )
            )

        document_output = DocumentOutput(contradictions=contradictions)

        workflow_info = workflow.info()
        parent_run_id = workflow_info.parent.run_id if workflow_info.parent else workflow_info.run_id

        upload_input = UploadTemporalCheckpointInput(
            project_id=workflow_input.project_id,
            workflow_id=workflow_info.workflow_id,
            run_id=workflow_info.run_id,
            filename=f"plausibility_{workflow_input.document_id}_{parent_run_id}.json",
            payload=document_output.model_dump(mode="json"),
        )

        upload_response = await workflow.execute_activity(
            upload_temporal_checkpoint,
            upload_input,
            task_queue=workflow_info.task_queue,
            start_to_close_timeout=timedelta(seconds=config.TEMPORAL.ACTIVITY_TIMEOUT_SECONDS),
        )

        return upload_response
