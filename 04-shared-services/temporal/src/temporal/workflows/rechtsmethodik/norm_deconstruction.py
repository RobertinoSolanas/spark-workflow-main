from typing import Any

from temporal.utils import WorkflowName, execute_workflow, start_workflow
from temporal.workflows.rechtsmethodik.types import NormDekonstruktionInput, NormDekonstruktionOutput
from temporalio.client import WorkflowHandle
from temporalio.workflow import ChildWorkflowHandle

NORM_DEKONSTRUKTION_WORKFLOW_ID = WorkflowName("NormDekonstruktion")
TASK_QUEUE = "rechtsmethodik"


async def execute_rechtsmethodik_workflow(
    input: NormDekonstruktionInput, project_id: str | None = None
) -> NormDekonstruktionOutput:
    return await execute_workflow(
        workflow_id=NORM_DEKONSTRUKTION_WORKFLOW_ID, input=input, task_queue=TASK_QUEUE, project_id=project_id
    )


async def start_rechtsmethodik_workflow(
    input: NormDekonstruktionInput, project_id: str | None = None
) -> WorkflowHandle[Any, NormDekonstruktionOutput] | ChildWorkflowHandle[Any, NormDekonstruktionOutput]:
    return await start_workflow(
        workflow_id=NORM_DEKONSTRUKTION_WORKFLOW_ID, input=input, task_queue=TASK_QUEUE, project_id=project_id
    )
