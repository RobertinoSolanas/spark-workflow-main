from typing import Any

from temporal.utils import WorkflowName, execute_workflow, start_workflow
from temporal.workflows.modul_suche_und_zuordnung.types import (
    NormOrchestratorWorkflowInput,
    NormOrchestratorWorkflowOutput,
)
from temporalio.client import WorkflowHandle
from temporalio.workflow import ChildWorkflowHandle

NORM_ORCHESTRATOR_WORKFLOW_ID = WorkflowName("norm_orchestrator")
TASK_QUEUE = "modul-suche-und-zuordnung"


async def execute_norm_orchestrator_workflow(
    input: NormOrchestratorWorkflowInput, project_id: str | None = None
) -> NormOrchestratorWorkflowOutput:
    return await execute_workflow(
        workflow_id=NORM_ORCHESTRATOR_WORKFLOW_ID, input=input, task_queue=TASK_QUEUE, project_id=project_id
    )


async def start_norm_orchestrator_workflow(
    input: NormOrchestratorWorkflowInput, project_id: str | None = None
) -> WorkflowHandle[Any, NormOrchestratorWorkflowOutput] | ChildWorkflowHandle[Any, NormOrchestratorWorkflowOutput]:
    return await start_workflow(
        workflow_id=NORM_ORCHESTRATOR_WORKFLOW_ID, input=input, task_queue=TASK_QUEUE, project_id=project_id
    )
