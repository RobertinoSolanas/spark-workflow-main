import logging
from datetime import datetime
from typing import Any, TypedDict
from uuid import UUID

from src.models.schemas.job_service_schemas import (
    ChildWorkflowInfo,
    ExecutionStatus,
    GetWorkflowExecutionTreeResponse,
    GetWorkflowResponse,
    GetWorkflowsResponse,
    HistoryNode,
    TemporalStatus,
)
from temporalio.api.enums.v1.event_type_pb2 import EventType
from temporalio.client import Client

logger = logging.getLogger(__name__)


class ChildWorkflowState(TypedDict):
    workflow_id: str
    workflow_type: str
    status: TemporalStatus
    error: str | None


class StatusInfo(TypedDict):
    time: datetime | None
    workflow_id: str | None


class JobServiceService:
    @staticmethod
    async def get_workflows(
        execution_status: ExecutionStatus,
        project_id: UUID,
        temporal_client: Client,
    ) -> GetWorkflowsResponse:
        """
        Retrieve a paginated list of Temporal jobs (workflows) with optional filtering.
        """
        latest_status_info: dict[ExecutionStatus, StatusInfo] = {
            status: {"time": None, "workflow_id": None}
            for status in [
                ExecutionStatus.RUNNING,
                ExecutionStatus.COMPLETED,
                ExecutionStatus.FAILED,
                ExecutionStatus.CANCELED,
                ExecutionStatus.TERMINATED,
                ExecutionStatus.TIMED_OUT,
                ExecutionStatus.CONTINUED_AS_NEW,
            ]
        }

        query_parts = ["`ParentWorkflowId` IS null"]
        if execution_status != ExecutionStatus.ALL:
            query_parts.append(f'`ExecutionStatus` = "{execution_status.value}"')
        query_parts.append(f'`ProjectId` = "{project_id}"')
        query = " AND ".join(query_parts)

        iterator = temporal_client.list_workflows(query)

        workflows = []
        async for workflow in iterator:
            project_id_value = None
            if workflow.search_attributes and "ProjectId" in workflow.search_attributes:
                project_id_value = workflow.search_attributes["ProjectId"][0]

            # Fetch child workflows 2 levels deep
            try:
                tree = await JobServiceService.build_history_tree(
                    temporal_client, workflow.id, max_depth=2
                )
                children = await JobServiceService._history_to_children(tree)
            except Exception:
                logger.warning(
                    "Failed to fetch child workflows for %s", workflow.id, exc_info=True
                )
                children = []

            partial = {
                "workflow_id": workflow.id,
                "project_id": project_id_value,
                "workflow_type": workflow.workflow_type,
                "status": workflow.status.name.lower() if workflow.status else None,
                "workflow_start_time": workflow.start_time,
                "workflow_close_time": workflow.close_time,
                "children": children,
            }
            workflows.append(partial)

            status_str = workflow.status.name if workflow.status is not None else None
            ts = workflow.close_time or workflow.start_time

            if not ts:
                continue

            def is_effective_status(enum_value: ExecutionStatus) -> bool:
                return (
                    execution_status == ExecutionStatus.ALL
                    or execution_status == enum_value
                )

            if status_str:
                status_str_lower = status_str.lower()
                for status_enum in latest_status_info.keys():
                    if (
                        status_str_lower == status_enum.value.lower()
                        and is_effective_status(status_enum)
                    ):
                        current_time = latest_status_info[status_enum]["time"]
                        if current_time is None or ts > current_time:
                            latest_status_info[status_enum]["time"] = ts
                            latest_status_info[status_enum]["workflow_id"] = (
                                workflow.id
                            )
                        break

        status_to_field = {
            ExecutionStatus.RUNNING: "latest_running_workflow_id",
            ExecutionStatus.COMPLETED: "latest_completed_workflow_id",
            ExecutionStatus.FAILED: "latest_failed_workflow_id",
            ExecutionStatus.CANCELED: "latest_canceled_workflow_id",
            ExecutionStatus.TERMINATED: "latest_terminated_workflow_id",
            ExecutionStatus.TIMED_OUT: "latest_timed_out_workflow_id",
            ExecutionStatus.CONTINUED_AS_NEW: "latest_continued_as_new_workflow_id",
        }

        response_kwargs: dict[str, Any] = {
            field_name: latest_status_info[status_enum]["workflow_id"]
            for status_enum, field_name in status_to_field.items()
        }
        response_kwargs.update(
            {
                "retrieved_workflows": len(workflows),
                "workflows": workflows,
            }
        )

        return GetWorkflowsResponse(**response_kwargs)

    @staticmethod
    async def get_workflow(
        workflow_id: str, temporal_client: Client
    ) -> GetWorkflowResponse:
        """Get a specific workflow based on its workflow id"""

        handle = temporal_client.get_workflow_handle(workflow_id=workflow_id)
        description = await handle.describe()
        result = None
        if description.close_time:
            result = await handle.result()

        try:
            tree = await JobServiceService.build_history_tree(
                temporal_client, workflow_id, max_depth=2
            )
            children = await JobServiceService._history_to_children(tree)
        except Exception:
            logger.warning(
                "Failed to fetch child workflows for %s", workflow_id, exc_info=True
            )
            children = []

        return GetWorkflowResponse(
            workflow_id=workflow_id,
            workflow_type=description.workflow_type,
            workflow_start_time=description.start_time,
            workflow_close_time=description.close_time,
            status=description.status.name.lower(),
            result=result,
            children=children,
        )

    @staticmethod
    async def build_history_tree(
        client: Client,
        workflow_id: str,
        run_id: str | None = None,
        max_depth: int | None = None,
        _current_depth: int = 0,
    ) -> HistoryNode:
        handle = client.get_workflow_handle(workflow_id, run_id=run_id)
        wf_history = await handle.fetch_history()

        node = HistoryNode(
            workflow_id=workflow_id,
            run_id=handle.run_id or run_id or "unknown",
            history=wf_history,
        )

        if max_depth is not None and _current_depth >= max_depth:
            return node

        for ev in wf_history.events:
            attrs = ev.child_workflow_execution_started_event_attributes
            if not attrs:
                continue

            child_exec = attrs.workflow_execution
            if not child_exec or not child_exec.workflow_id:
                continue
            child_node = await JobServiceService.build_history_tree(
                client,
                child_exec.workflow_id,
                child_exec.run_id,
                max_depth=max_depth,
                _current_depth=_current_depth + 1,
            )
            node.children.append(child_node)

        return node

    @staticmethod
    def _extract_child_workflows(
        events: Any,
    ) -> tuple[dict[int, ChildWorkflowState], dict[str, int]]:
        """Extract child workflow states from history events.

        Returns (child_workflows by initiated_event_id, workflow_id-to-initiated_id mapping).
        """
        child_workflows: dict[int, ChildWorkflowState] = {}
        child_wf_id_to_initiated: dict[str, int] = {}

        for event in events:
            if (
                event.event_type
                == EventType.EVENT_TYPE_START_CHILD_WORKFLOW_EXECUTION_INITIATED
            ):
                attrs = event.start_child_workflow_execution_initiated_event_attributes
                child_wf_id = attrs.workflow_id
                child_workflows[event.event_id] = {
                    "workflow_id": child_wf_id,
                    "workflow_type": attrs.workflow_type.name,
                    "status": "pending",
                    "error": None,
                }
                child_wf_id_to_initiated[child_wf_id] = event.event_id

            elif (
                event.event_type
                == EventType.EVENT_TYPE_CHILD_WORKFLOW_EXECUTION_STARTED
            ):
                initiated_id = event.child_workflow_execution_started_event_attributes.initiated_event_id
                if initiated_id in child_workflows:
                    child_workflows[initiated_id]["status"] = "running"

            elif (
                event.event_type
                == EventType.EVENT_TYPE_CHILD_WORKFLOW_EXECUTION_COMPLETED
            ):
                initiated_id = event.child_workflow_execution_completed_event_attributes.initiated_event_id
                if initiated_id in child_workflows:
                    child_workflows[initiated_id]["status"] = "completed"

            elif (
                event.event_type
                == EventType.EVENT_TYPE_CHILD_WORKFLOW_EXECUTION_FAILED
            ):
                attrs = event.child_workflow_execution_failed_event_attributes
                if attrs.initiated_event_id in child_workflows:
                    child_workflows[attrs.initiated_event_id]["status"] = "failed"
                    child_workflows[attrs.initiated_event_id]["error"] = attrs.failure.message

            elif (
                event.event_type
                == EventType.EVENT_TYPE_CHILD_WORKFLOW_EXECUTION_CANCELED
            ):
                attrs = event.child_workflow_execution_canceled_event_attributes
                if attrs.initiated_event_id in child_workflows:
                    child_workflows[attrs.initiated_event_id]["status"] = "failed"
                    child_workflows[attrs.initiated_event_id]["error"] = str(attrs.details)

            elif (
                event.event_type
                == EventType.EVENT_TYPE_CHILD_WORKFLOW_EXECUTION_TIMED_OUT
            ):
                initiated_id = event.child_workflow_execution_timed_out_event_attributes.initiated_event_id
                if initiated_id in child_workflows:
                    child_workflows[initiated_id]["status"] = "failed"
                    child_workflows[initiated_id]["error"] = "Child workflow timed out"

            elif (
                event.event_type
                == EventType.EVENT_TYPE_CHILD_WORKFLOW_EXECUTION_TERMINATED
            ):
                initiated_id = event.child_workflow_execution_terminated_event_attributes.initiated_event_id
                if initiated_id in child_workflows:
                    child_workflows[initiated_id]["status"] = "failed"
                    child_workflows[initiated_id]["error"] = "Child workflow terminated"

        return child_workflows, child_wf_id_to_initiated

    @staticmethod
    async def history_to_status(node: HistoryNode) -> dict[str, Any]:
        activities: dict[int, dict[str, Any]] = {}

        workflow_name = ""
        workflow_status = "running"
        workflow_error = None

        for event in node.history.events:
            event_id = event.event_id

            if event.event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_STARTED:
                attrs = event.workflow_execution_started_event_attributes
                workflow_name = attrs.workflow_type.name

            elif event.event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED:
                workflow_status = "completed"

            elif event.event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_FAILED:
                attrs = event.workflow_execution_failed_event_attributes
                workflow_status = "failed"
                workflow_error = attrs.failure.message

            elif event.event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_CANCELED:
                attrs = event.workflow_execution_canceled_event_attributes
                workflow_status = "failed"
                workflow_error = str(attrs.details)

            elif event.event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_TERMINATED:
                attrs = event.workflow_execution_terminated_event_attributes
                workflow_status = "failed"
                workflow_error = attrs.reason

            elif event.event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_TIMED_OUT:
                workflow_status = "failed"
                workflow_error = "Workflow timed out"

            elif event.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED:
                attrs = event.activity_task_scheduled_event_attributes
                activities[event_id] = {
                    "type": "activity",
                    "name": attrs.activity_type.name,
                    "id": attrs.activity_id,
                    "status": "pending",
                    "error": None,
                    "children": [],
                }

            elif event.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_STARTED:
                scheduled_id = event.activity_task_started_event_attributes.scheduled_event_id
                if scheduled_id in activities:
                    activities[scheduled_id]["status"] = "running"

            elif event.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_COMPLETED:
                scheduled_id = event.activity_task_completed_event_attributes.scheduled_event_id
                if scheduled_id in activities:
                    activities[scheduled_id]["status"] = "completed"

            elif event.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_FAILED:
                attrs = event.activity_task_failed_event_attributes
                if attrs.scheduled_event_id in activities:
                    activities[attrs.scheduled_event_id]["status"] = "failed"
                    activities[attrs.scheduled_event_id]["error"] = attrs.failure.message

            elif event.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_TIMED_OUT:
                scheduled_id = event.activity_task_timed_out_event_attributes.scheduled_event_id
                if scheduled_id in activities:
                    activities[scheduled_id]["status"] = "failed"
                    activities[scheduled_id]["error"] = "Activity timed out"

            elif event.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_CANCELED:
                attrs = event.activity_task_canceled_event_attributes
                if attrs.scheduled_event_id in activities:
                    activities[attrs.scheduled_event_id]["status"] = "failed"
                    activities[attrs.scheduled_event_id]["error"] = str(attrs.details)

        child_states, child_wf_id_to_initiated = (
            JobServiceService._extract_child_workflows(node.history.events)
        )

        child_wf_dicts: dict[int, dict[str, Any]] = {
            eid: {
                "type": "workflow",
                "name": state["workflow_type"],
                "id": state["workflow_id"],
                "status": state["status"],
                "error": state["error"],
                "children": [],
            }
            for eid, state in child_states.items()
        }

        for child_node in node.children:
            child_id = child_node.workflow_id
            if child_id in child_wf_id_to_initiated:
                initiated_id = child_wf_id_to_initiated[child_id]
                if initiated_id in child_wf_dicts:
                    child_status = await JobServiceService.history_to_status(child_node)
                    child_wf_dicts[initiated_id]["children"] = child_status.get(
                        "children", []
                    )
                    if child_status.get("status"):
                        child_wf_dicts[initiated_id]["status"] = child_status["status"]
                    if child_status.get("error"):
                        child_wf_dicts[initiated_id]["error"] = child_status["error"]

        all_children = []
        for eid in sorted(set(activities.keys()) | set(child_wf_dicts.keys())):
            if eid in activities:
                all_children.append(activities[eid])
            if eid in child_wf_dicts:
                all_children.append(child_wf_dicts[eid])

        return {
            "type": "workflow",
            "name": workflow_name,
            "id": node.workflow_id,
            "status": workflow_status,
            "error": workflow_error,
            "children": all_children,
        }

    @staticmethod
    async def _history_to_children(node: HistoryNode) -> list[ChildWorkflowInfo]:
        """Extract child workflow info from a HistoryNode."""
        child_states, child_wf_id_to_initiated = (
            JobServiceService._extract_child_workflows(node.history.events)
        )

        for child_node in node.children:
            child_id = child_node.workflow_id
            if child_id in child_wf_id_to_initiated:
                initiated_id = child_wf_id_to_initiated[child_id]
                if initiated_id in child_states:
                    grandchildren = await JobServiceService._history_to_children(
                        child_node
                    )
                    child_states[initiated_id]["children"] = grandchildren

        return [
            ChildWorkflowInfo(**child_states[eid])
            for eid in sorted(child_states.keys())
        ]

    @staticmethod
    async def get_workflow_execution_tree(
        temporal_client: Client, workflow_id: str
    ) -> GetWorkflowExecutionTreeResponse:
        """Get the execution tree of a given workflow using its workflow id"""
        root_node = await JobServiceService.build_history_tree(
            temporal_client, workflow_id
        )
        status = await JobServiceService.history_to_status(root_node)
        return GetWorkflowExecutionTreeResponse(**status)
