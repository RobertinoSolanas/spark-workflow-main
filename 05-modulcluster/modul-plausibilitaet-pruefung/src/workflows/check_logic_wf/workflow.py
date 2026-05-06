from temporalio import workflow
from temporalio.common import WorkflowIDReusePolicy

from src.config.config import config
from src.workflows.check_logic_wf.single_document_workflow import (
    PlausibilityCheckSingleDocumentWorkflow,
)
from src.workflows.input_schemas import (
    OrchestratorInputSchema,
    SingleDocumentWorkflowInputSchema,
)

PLAUSIBILITY_CHECK_ORCHESTRATOR_WORKFLOW_ID = "plausibility-check-orchestrator"

with workflow.unsafe.imports_passed_through():
    from src.activities.dms_activities import (
        AggregateCheckpointsInput,
        aggregate_and_upload_checkpoints,
    )
    from src.dms.schemas import DMSFileResponse
    from src.workflows.utils import sliding_window

@workflow.defn
class PlausibilityCheckOrchestratorWorkflow:
    """Orchestrates document-level plausibility checks and aggregates checkpoints."""

    @workflow.run
    async def run(self, workflow_input: OrchestratorInputSchema) -> DMSFileResponse:
        """Run one child workflow per document and upload an aggregated result."""

        orchestrator_id = workflow.info().workflow_id
        task_queue = workflow.info().task_queue

        checkpoint_file_responses = await sliding_window(
            workflow_input.document_ids,
            lambda doc_id: workflow.execute_child_workflow(
                PlausibilityCheckSingleDocumentWorkflow.run,
                arg=SingleDocumentWorkflowInputSchema(
                    project_id=workflow_input.project_id,
                    document_id=doc_id,
                ),
                task_queue=task_queue,
                id=f"{orchestrator_id}/doc/{doc_id}",
                id_reuse_policy=WorkflowIDReusePolicy.TERMINATE_IF_RUNNING,
            ),
            concurrency=config.TEMPORAL.MAX_PENDING_ACTIVITIES,
        )

        workflow.logger.info("All documents processed and uploaded successfully")
        workflow_info = workflow.info()
        checkpoint_file_ids = [
            file_response.id for file_response in checkpoint_file_responses
        ]
        aggregation_input = AggregateCheckpointsInput(
            project_id=workflow_input.project_id,
            workflow_id=workflow_info.workflow_id,
            run_id=workflow_info.run_id,
            filename=f"aggregated_plausibility_results_{workflow_info.run_id}.json",
            file_ids=checkpoint_file_ids,
        )
        final_response = await workflow.execute_activity(
            aggregate_and_upload_checkpoints,
            arg=aggregation_input,
            task_queue=workflow.info().task_queue,
            start_to_close_timeout=workflow.timedelta(
                seconds=config.TEMPORAL.ACTIVITY_TIMEOUT_SECONDS
            ),
        )

        return final_response
