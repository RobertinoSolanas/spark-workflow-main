from typing import Any

from temporal.utils import WorkflowName, execute_workflow, start_workflow
from temporalio.client import WorkflowHandle
from temporalio.workflow import ChildWorkflowHandle

from .types import DMSFileResponse, InhaltsverzeichnisMatchingParams

TASK_QUEUE = "formale-pruefung"
INHALTSVERZEICHNIS_MATCHING_WORKFLOW_ID = WorkflowName("InhaltsverzeichnisMatchingWorkflow")


async def execute_inhaltsverzeichnis_matching_workflow(
    input: InhaltsverzeichnisMatchingParams, project_id: str | None = None
) -> DMSFileResponse:
    return await execute_workflow(
        workflow_id=INHALTSVERZEICHNIS_MATCHING_WORKFLOW_ID, input=input, task_queue=TASK_QUEUE, project_id=project_id
    )


async def start_inhaltsverzeichnis_matching_workflow(
    input: InhaltsverzeichnisMatchingParams, project_id: str | None = None
) -> WorkflowHandle[Any, DMSFileResponse] | ChildWorkflowHandle[Any, DMSFileResponse]:
    return await start_workflow(
        workflow_id=INHALTSVERZEICHNIS_MATCHING_WORKFLOW_ID, input=input, task_queue=TASK_QUEUE, project_id=project_id
    )
