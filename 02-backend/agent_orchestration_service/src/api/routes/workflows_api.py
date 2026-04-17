from event_logging.enums import (
    EventAction,
    EventCategory,
    EventOutcome,
    LogEventDefault,
)
from fastapi import APIRouter, HTTPException, status
from temporal import stop_workflow

from src.models.schemas.temporal.fvp import (
    FVPWorkflowArgs,
    FVPWorkflowRequest,
)
from src.models.schemas.workflows import (
    CancelWorkflowResponse,
    WorkflowResponse,
)
from src.services.workflows.fvp import start_fvp_workflow
from src.utils.logger import logger

router = APIRouter(prefix="/workflows", tags=["Workflows"])


@router.post("/formale-pruefung", response_model=WorkflowResponse)
async def orchestrate_fvp_workflow(payload: FVPWorkflowRequest) -> WorkflowResponse:
    """
    Orchestrate a FVP (Formale Vollständigkeitsprüfung) workflow.

    Args:
        payload (FVPWorkflowRequest): The payload containing the project ID.

    Returns:
        WorkflowResponse: The response containing the workflow ID.
    """
    handle = await start_fvp_workflow(
        FVPWorkflowArgs(project_id=payload.project_id),
        project_id=payload.project_id,
    )
    return WorkflowResponse(parent_job_id=handle.id)


@router.post("/cancel/{workflow_id}", response_model=CancelWorkflowResponse)
async def cancel_workflow(workflow_id: str) -> CancelWorkflowResponse:
    """
    Cancel a running workflow.

    Args:
        workflow_id (str): The ID of the workflow to cancel.

    Returns:
        CancelWorkflowResponse: The response confirming the cancellation request.

    Raises:
        HTTPException: If the workflow is not found or cancellation fails.
    """
    try:
        await stop_workflow(workflow_id)
        logger.info(
            action=EventAction.NOTIFY,
            outcome=EventOutcome.SUCCESS,
            category=EventCategory.API,
            default_event=LogEventDefault.GENERAL,
            message=f"Stopped workflow {workflow_id}",
        )
        return CancelWorkflowResponse(workflow_id=workflow_id)
    except Exception as e:
        logger.warn(
            action=EventAction.NOTIFY,
            outcome=EventOutcome.FAILURE,
            category=EventCategory.API,
            default_event=LogEventDefault.GENERAL,
            message=f"Failed to stop workflow {workflow_id}: {e}",
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop workflow {workflow_id}",
        ) from e
