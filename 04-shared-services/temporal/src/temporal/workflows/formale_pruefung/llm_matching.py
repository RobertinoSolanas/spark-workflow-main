from typing import Any

from temporal.utils import WorkflowName, execute_workflow, start_workflow
from temporalio.client import WorkflowHandle
from temporalio.workflow import ChildWorkflowHandle

from .types import DMSFileResponse, LLMMatchingParams

TASK_QUEUE = "formale-pruefung"
LLM_MATCHING_WORKFLOW_ID = WorkflowName("LLMMatchingWorkflow")


async def execute_llm_matching_workflow(input: LLMMatchingParams, project_id: str | None = None) -> DMSFileResponse:
    return await execute_workflow(
        workflow_id=LLM_MATCHING_WORKFLOW_ID, input=input, task_queue=TASK_QUEUE, project_id=project_id
    )


async def start_llm_matching_workflow(
    input: LLMMatchingParams, project_id: str | None = None
) -> WorkflowHandle[Any, DMSFileResponse] | ChildWorkflowHandle[Any, DMSFileResponse]:
    return await start_workflow(
        workflow_id=LLM_MATCHING_WORKFLOW_ID, input=input, task_queue=TASK_QUEUE, project_id=project_id
    )
