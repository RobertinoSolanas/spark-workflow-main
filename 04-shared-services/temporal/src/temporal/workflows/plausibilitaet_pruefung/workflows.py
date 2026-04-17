from typing import Any

from temporal.utils import WorkflowName, execute_workflow, start_workflow
from temporal.workflows.plausibilitaet_pruefung.types import DMSFileResponse, PlausibilityOrchestratorInput
from temporalio.client import WorkflowHandle
from temporalio.workflow import ChildWorkflowHandle

TASK_QUEUE = "plausibilitaet-pruefung"
PLAUSIBILITY_MAIN_ORCHESTRATOR_WORKFLOW_ID = WorkflowName("PlausibilityMainOrchestratorWorkflow")


async def execute_plausibility_orchestrator_workflow(
    input: PlausibilityOrchestratorInput, project_id: str | None = None
) -> DMSFileResponse:
    return await execute_workflow(
        workflow_id=PLAUSIBILITY_MAIN_ORCHESTRATOR_WORKFLOW_ID,
        input=input,
        task_queue=TASK_QUEUE,
        project_id=project_id,
    )


async def start_plausibility_orchestrator_workflow(
    input: PlausibilityOrchestratorInput, project_id: str | None = None
) -> WorkflowHandle[Any, DMSFileResponse] | ChildWorkflowHandle[Any, DMSFileResponse]:
    return await start_workflow(
        workflow_id=PLAUSIBILITY_MAIN_ORCHESTRATOR_WORKFLOW_ID,
        input=input,
        task_queue=TASK_QUEUE,
        project_id=project_id,
    )
