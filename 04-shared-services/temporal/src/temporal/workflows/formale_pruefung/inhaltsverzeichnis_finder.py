from typing import Any

from temporal.utils import WorkflowName, execute_workflow, start_workflow
from temporalio.client import WorkflowHandle
from temporalio.workflow import ChildWorkflowHandle

from .types import InhaltsverzeichnisFinderOutput, InhaltsverzeichnisFinderParams

TASK_QUEUE = "formale-pruefung"
INHALTSVERZEICHNIS_FINDER_WORKFLOW_ID = WorkflowName("InhaltsverzeichnisFinderWorkflow")


async def execute_inhaltsverzeichnis_finder_workflow(
    input: InhaltsverzeichnisFinderParams, project_id: str | None = None
) -> InhaltsverzeichnisFinderOutput:
    return await execute_workflow(
        workflow_id=INHALTSVERZEICHNIS_FINDER_WORKFLOW_ID, input=input, task_queue=TASK_QUEUE, project_id=project_id
    )


async def start_inhaltsverzeichnis_finder_workflow(
    input: InhaltsverzeichnisFinderParams, project_id: str | None = None
) -> WorkflowHandle[Any, InhaltsverzeichnisFinderOutput] | ChildWorkflowHandle[Any, InhaltsverzeichnisFinderOutput]:
    return await start_workflow(
        workflow_id=INHALTSVERZEICHNIS_FINDER_WORKFLOW_ID, input=input, task_queue=TASK_QUEUE, project_id=project_id
    )
