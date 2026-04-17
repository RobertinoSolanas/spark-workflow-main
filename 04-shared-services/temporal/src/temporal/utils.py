from typing import Any, NewType

from temporalio import workflow
from temporalio.client import WorkflowHandle
from temporalio.common import (
    SearchAttributeKey,
    SearchAttributePair,
    TypedSearchAttributes,
    WorkflowIDConflictPolicy,
    WorkflowIDReusePolicy,
)
from temporalio.exceptions import TemporalError
from temporalio.workflow import ChildWorkflowHandle
from ulid import ULID

from temporal.observability import traced
from temporal.worker import get_temporal_client

WorkflowName = NewType("WorkflowName", str)
PROJECT_ID_SEARCH_ATTRIBUTE = SearchAttributeKey.for_keyword("ProjectId")


def _search_attributes(project_id: str | None) -> TypedSearchAttributes | None:
    if project_id is None:
        return None
    return TypedSearchAttributes([SearchAttributePair(PROJECT_ID_SEARCH_ATTRIBUTE, project_id)])


def is_in_workflow() -> bool:
    try:
        workflow.info()
        return True
    except (RuntimeError, TemporalError):
        return False


@traced
async def execute_workflow(
    workflow_id: WorkflowName,
    input: Any,
    task_queue: str,
    project_id: str | None = None,
    id_reuse_policy: WorkflowIDReusePolicy = WorkflowIDReusePolicy.ALLOW_DUPLICATE,
    id_conflict_policy: WorkflowIDConflictPolicy = WorkflowIDConflictPolicy.UNSPECIFIED,
) -> Any:
    sa = _search_attributes(project_id)
    if is_in_workflow():
        return await workflow.execute_child_workflow(
            workflow_id,
            input,
            id=str(workflow.uuid4()),
            task_queue=task_queue,
            search_attributes=sa,
            id_reuse_policy=id_reuse_policy,
        )
    client = await get_temporal_client()
    return await client.execute_workflow(
        workflow_id,
        input,
        id=str(ULID()),
        task_queue=task_queue,
        search_attributes=sa,
        id_reuse_policy=id_reuse_policy,
        id_conflict_policy=id_conflict_policy,
    )


@traced
async def start_workflow(
    workflow_id: WorkflowName,
    input: Any,
    task_queue: str,
    project_id: str | None = None,
    id_reuse_policy: WorkflowIDReusePolicy = WorkflowIDReusePolicy.ALLOW_DUPLICATE,
    id_conflict_policy: WorkflowIDConflictPolicy = WorkflowIDConflictPolicy.UNSPECIFIED,
) -> WorkflowHandle[Any, Any] | ChildWorkflowHandle[Any, Any]:
    sa = _search_attributes(project_id)
    if is_in_workflow():
        return await workflow.start_child_workflow(
            workflow_id,
            input,
            id=str(workflow.uuid4()),
            task_queue=task_queue,
            search_attributes=sa,
            id_reuse_policy=id_reuse_policy,
        )
    client = await get_temporal_client()
    return await client.start_workflow(
        workflow_id,
        input,
        id=str(ULID()),
        task_queue=task_queue,
        search_attributes=sa,
        id_reuse_policy=id_reuse_policy,
        id_conflict_policy=id_conflict_policy,
    )


@traced
async def stop_workflow(workflow_id: str) -> None:
    client = await get_temporal_client()
    await client.get_workflow_handle(workflow_id).cancel()
