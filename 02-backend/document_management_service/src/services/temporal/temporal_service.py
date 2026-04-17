from collections.abc import Awaitable, Callable
from typing import Any

from event_logging.enums import (
    EventAction,
    EventCategory,
    EventOutcome,
)
from temporalio.client import Client, WorkflowHandle
from temporalio.common import (
    SearchAttributeKey,
    SearchAttributePair,
    TypedSearchAttributes,
    WorkflowIDConflictPolicy,
    WorkflowIDReusePolicy,
)
from temporalio.exceptions import TemporalError, WorkflowAlreadyStartedError

from src.config.settings import settings
from src.models.db.workflow_enum import ApprovalStatus, WorkflowStatusEnum
from src.models.schemas.approval_schema import FileDiffResponse
from src.services.temporal.temporal_client import get_temporal_client
from src.services.temporal.temporal_utils import validate_user_diff
from src.utils.exceptions import (
    WorkflowAlreadyApprovedError,
    WorkflowAlreadyRejectedError,
    WorkflowIncorrectStatusError,
    WorkflowNotFoundError,
)
from src.utils.logger import logger

PROJECT_ID_SEARCH_ATTRIBUTE = SearchAttributeKey.for_keyword("ProjectId")
WORKFLOW_NOT_FOUND_STRING = "workflow not found"


class TemporalWorkflowService:
    """
    Service for managing Temporal workflows: start, signal, query, cancel.

    Provides clean high-level methods especially useful for human-in-the-loop
    confirmation/approval flows.
    """

    def __init__(self):
        self._client: Client | None = None

    async def _get_client(self) -> Client:
        """Lazily initialize and return Temporal client."""
        if self._client is None:
            self._client = await get_temporal_client()
        return self._client

    @staticmethod
    async def _handle_missing_workflow_error(exc: Exception, workflow_id: str) -> None:
        """Helper method to handle missing workflow errors."""
        if WORKFLOW_NOT_FOUND_STRING in str(exc):
            message = f"Workflow not found workflow {workflow_id}: {exc}"
            logger.error(
                action=EventAction.READ,
                outcome=EventOutcome.FAILURE,
                category=EventCategory.SERVICE,
                message=message,
                exc_info=True,
            )
            raise WorkflowNotFoundError(message) from exc

    async def run_workflow(
        self,
        workflow: str | Callable[..., Awaitable[Any]],
        workflow_input: Any,
        workflow_id: str,
        project_id: str | None = None,
    ) -> WorkflowHandle:
        """
        Start a new workflow execution.

        Args:
            workflow: Workflow awaitable
            workflow_input: Input arguments
            workflow_id: Custom ID
            project_id: Optional project ID for search attributes

        Returns:
            str: The workflow ID of the started execution
        """
        client = await self._get_client()

        search_attributes: TypedSearchAttributes | None = None
        if project_id:
            search_attributes = TypedSearchAttributes(
                [SearchAttributePair(PROJECT_ID_SEARCH_ATTRIBUTE, project_id)]
            )
        try:
            handle = await client.start_workflow(
                workflow,
                arg=workflow_input,
                id=workflow_id,
                task_queue=settings.TEMPORAL.TASK_QUEUE,
                id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY,
                id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
                search_attributes=search_attributes,
            )
        except WorkflowAlreadyStartedError as exc:
            handle = client.get_workflow_handle(
                workflow_id=workflow_id,
                run_id=exc.run_id,
            )

        return handle

    async def get_approval_status(self, workflow_id: str) -> ApprovalStatus:
        """
        Query current human approval status of a workflow.

        Returns:
            ApprovalStatus: The status of the workflow approval step
        """
        client = await self._get_client()
        handle = client.get_workflow_handle(workflow_id=workflow_id)

        try:
            status = await handle.query("get_approval_status")
            return status
        except TemporalError as exc:
            await self._handle_missing_workflow_error(exc=exc, workflow_id=workflow_id)
            logger.error(
                action=EventAction.READ,
                outcome=EventOutcome.FAILURE,
                category=EventCategory.SERVICE,
                message=(
                    f"Could not get approval status of workflow {workflow_id}: {exc}"
                ),
                exc_info=True,
            )
            raise

    async def is_awaiting_approval(self, workflow_id: str) -> bool:
        """
        Check if workflow is still waiting for human confirmation.

        Args:
            workflow_id: Workflow ID

        Returns:
            True if the workflow is still waiting for human confirmation
        """
        status = await self.get_approval_status(workflow_id)
        return status == ApprovalStatus.PENDING

    async def approve_workflow(self, workflow_id: str) -> None:
        """
        Signal workflow to approve (unblocks waiting condition).

        Args:
            workflow_id: Workflow ID
        """
        client = await self._get_client()
        handle = client.get_workflow_handle(workflow_id)
        approval_status = await self.get_approval_status(workflow_id)

        desc = await handle.describe()
        if not desc.status:
            raise ValueError(f"Workflow {workflow_id} has no status")

        workflow_status = WorkflowStatusEnum(desc.status.name)

        if (
            workflow_status != WorkflowStatusEnum.REQUIRES_APPROVAL
            and approval_status != ApprovalStatus.PENDING
        ):
            message = (
                f"Approve skipped for {workflow_id} — "
                f"workflow does not require approval."
            )
            logger.info(
                action=EventAction.WRITE,
                outcome=EventOutcome.FAILURE,
                category=EventCategory.SERVICE,
                message=message,
            )
            raise WorkflowIncorrectStatusError(message)

        elif approval_status == ApprovalStatus.REJECTED:
            message = f"Approve skipped for {workflow_id} — workflow already rejected."
            logger.info(
                action=EventAction.WRITE,
                outcome=EventOutcome.FAILURE,
                category=EventCategory.SERVICE,
                message=message,
            )
            raise WorkflowAlreadyRejectedError(message)

        elif approval_status == ApprovalStatus.APPROVED:
            logger.info(
                action=EventAction.WRITE,
                outcome=EventOutcome.FAILURE,
                category=EventCategory.SERVICE,
                message=f"Approve skipped for {workflow_id} — already approved",
            )
            return

        try:
            await handle.signal("approve_upload")
        except TemporalError as exc:
            await self._handle_missing_workflow_error(exc=exc, workflow_id=workflow_id)
            logger.error(
                action=EventAction.WRITE,
                outcome=EventOutcome.FAILURE,
                category=EventCategory.SERVICE,
                message=f"Approve signal failed for {workflow_id}: {exc}",
                exc_info=True,
            )
            raise

    async def reject_workflow(self, workflow_id: str) -> None:
        """
        Signal workflow to reject (usually causes early exit).

        Args:
            workflow_id: Workflow ID
        """
        client = await self._get_client()
        handle = client.get_workflow_handle(workflow_id)
        approval_status = await self.get_approval_status(workflow_id)

        desc = await handle.describe()
        if not desc.status:
            raise ValueError(f"Workflow {workflow_id} has no status")
        workflow_status = WorkflowStatusEnum(desc.status.name)

        if (
            workflow_status != WorkflowStatusEnum.REQUIRES_APPROVAL
            and approval_status != ApprovalStatus.PENDING
        ):
            message = (
                f"Reject skipped for {workflow_id} — "
                f"workflow does not require approval."
            )
            logger.info(
                action=EventAction.WRITE,
                outcome=EventOutcome.FAILURE,
                category=EventCategory.SERVICE,
                message=message,
            )
            raise WorkflowIncorrectStatusError(message)

        elif approval_status == ApprovalStatus.APPROVED:
            message = f"Reject skipped for {workflow_id} — workflow already approved."
            logger.info(
                action=EventAction.WRITE,
                outcome=EventOutcome.FAILURE,
                category=EventCategory.SERVICE,
                message=message,
            )
            raise WorkflowAlreadyApprovedError(message)

        elif approval_status == ApprovalStatus.REJECTED:
            logger.info(
                action=EventAction.WRITE,
                outcome=EventOutcome.FAILURE,
                category=EventCategory.SERVICE,
                message=f"Reject skipped for {workflow_id} — already rejected",
            )
            return

        try:
            await handle.signal("reject_upload")
        except TemporalError as exc:
            await self._handle_missing_workflow_error(exc=exc, workflow_id=workflow_id)
            logger.error(
                action=EventAction.WRITE,
                outcome=EventOutcome.FAILURE,
                category=EventCategory.SERVICE,
                message=f"Reject signal failed for {workflow_id}: {exc}",
                exc_info=True,
            )
            raise

    async def cancel_workflow(self, workflow_id: str) -> None:
        """
        Request cancellation of a running workflow.

        Returns:
            bool: True if cancellation request was sent
        """
        client = await self._get_client()
        handle = client.get_workflow_handle(workflow_id)

        try:
            await handle.cancel()
        except TemporalError as exc:
            await self._handle_missing_workflow_error(exc=exc, workflow_id=workflow_id)
            logger.error(
                action=EventAction.WRITE,
                outcome=EventOutcome.FAILURE,
                category=EventCategory.SERVICE,
                message=f"Cancel request failed for {workflow_id}: {exc}",
                exc_info=True,
            )
            raise

    async def get_file_diff(self, workflow_id: str) -> FileDiffResponse | None:
        """
        Query the computed file diff from the workflow (for review/approval UI).

        Returns:
            The diff data (added/modified/deleted files, etc.) or None
            if not available (not computed yet or workflow finished).

        Raises:
            TemporalError: If query fails (e.g. workflow not found, closed)
        """
        client = await self._get_client()
        handle = client.get_workflow_handle(workflow_id=workflow_id)

        try:
            diff = await handle.query("get_diff_summary")
            return FileDiffResponse(**diff) if diff else None
        except TemporalError as exc:
            await self._handle_missing_workflow_error(exc=exc, workflow_id=workflow_id)
            logger.error(
                action=EventAction.READ,
                outcome=EventOutcome.FAILURE,
                category=EventCategory.SERVICE,
                message=f"Failed to query file diff for {workflow_id}: {exc}",
                exc_info=True,
            )
            raise

    async def set_file_diff(
        self, workflow_id: str, diff: FileDiffResponse
    ) -> FileDiffResponse:
        """
        Signal the workflow to update/store the computed file diff.

        This is typically called by the activity/workflow after diff computation.
        The new diff input is validated against a rule set.

        Raises:
            TemporalError: If signal fails (e.g. workflow not found, closed, rejected)
        """
        client = await self._get_client()
        handle = client.get_workflow_handle(workflow_id=workflow_id)

        try:
            current_diff = await self.get_file_diff(workflow_id=workflow_id)
            await validate_user_diff(current_diff=current_diff, user_diff=diff)
            await handle.signal("set_diff_summary", args=[diff.model_dump(mode="json")])
            logger.info(
                action=EventAction.WRITE,
                outcome=EventOutcome.SUCCESS,
                category=EventCategory.SERVICE,
                message=f"File diff updated for workflow {workflow_id}",
            )
            return diff
        except TemporalError as exc:
            await self._handle_missing_workflow_error(exc=exc, workflow_id=workflow_id)
            logger.error(
                action=EventAction.WRITE,
                outcome=EventOutcome.FAILURE,
                category=EventCategory.SERVICE,
                message=f"Failed to set file diff for {workflow_id}: {exc}",
                exc_info=True,
            )
            raise
