from uuid import UUID

import temporalio
from event_logging.enums import (
    EventAction,
    EventCategory,
    EventOutcome,
    LogEventDefault,
)
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from temporalio.client import Client

from src.models.schemas.job_service_schemas import (
    ExecutionStatus,
    GetWorkflowExecutionTreeResponse,
    GetWorkflowResponse,
    GetWorkflowsResponse,
)
from src.services.job_service_service import JobServiceService
from src.temporal.client import get_temporal_client
from src.utils.logger import logger

router = APIRouter(prefix="/temporal", tags=["Temporal"])
service = JobServiceService()


@router.get(
    "/workflows",
    response_model=GetWorkflowsResponse,
    status_code=status.HTTP_200_OK,
)
async def get_workflows(
    execution_status: ExecutionStatus = Query(
        ExecutionStatus.ALL, description="Which type of workflow to show"
    ),
    project_id: UUID = Query(..., description="The 'Verfahren' to filter on"),
    temporal_client: Client = Depends(get_temporal_client),
) -> GetWorkflowsResponse:
    """
    Retrieve a paginated list of Temporal jobs (workflows) with optional filtering.

    This method queries the Temporal server for workflows matching the given filters and returns
    information about the workflows, including the latest workflow IDs,
    and detailed execution info for each matched workflow.
    """
    try:
        response = await service.get_workflows(
            execution_status=execution_status,
            project_id=project_id,
            temporal_client=temporal_client,
        )
        return response
    except Exception as e:
        logger.warn(
            action=EventAction.ACCESS,
            outcome=EventOutcome.FAILURE,
            category=EventCategory.API,
            default_event=LogEventDefault.API_RESPONSE,
            message=f"Error retrieving workflows: {str(e)}",
        )
        raise HTTPException(
            status_code=500, detail="An error occurred during workflow retrieval"
        )


@router.get(
    "/workflows/{workflow_id}",
    response_model=GetWorkflowResponse,
    status_code=status.HTTP_200_OK,
)
async def get_workflow(
    workflow_id: str = Path(
        ..., description="The workflow id that you want to retrieve"
    ),
    temporal_client: Client = Depends(get_temporal_client),
) -> GetWorkflowResponse:
    """Gets the status of a given workflow using its id. If the result is ready at the time of executing this route returns the result as well.<br />"""
    try:
        response = await service.get_workflow(
            workflow_id=workflow_id, temporal_client=temporal_client
        )
        return response
    except temporalio.service.RPCError as exc:
        if "workflow not found for id" in str(exc).lower():
            logger.warn(
                action=EventAction.ACCESS,
                outcome=EventOutcome.FAILURE,
                category=EventCategory.API,
                default_event=LogEventDefault.API_RESPONSE,
                message=f"workflow id does not exist: {workflow_id}",
            )
            raise HTTPException(
                status_code=404, detail=f"Workflow does not exist: {workflow_id}"
            )
        logger.warn(
            action=EventAction.ACCESS,
            outcome=EventOutcome.FAILURE,
            category=EventCategory.API,
            default_event=LogEventDefault.API_RESPONSE,
            message=f"Error retrieving workflow: {str(exc)}",
        )
        raise HTTPException(
            status_code=500, detail="An error occurred during workflow retrieval"
        )
    except Exception as e:
        logger.warn(
            action=EventAction.ACCESS,
            outcome=EventOutcome.FAILURE,
            category=EventCategory.API,
            default_event=LogEventDefault.API_RESPONSE,
            message=f"Error retrieving workflow: {str(e)}",
        )
        raise HTTPException(
            status_code=500, detail="An error occurred during workflow retrieval"
        )


@router.get(
    "/workflows/{workflow_id}/execution-tree",
    response_model=GetWorkflowExecutionTreeResponse,
    status_code=status.HTTP_200_OK,
)
async def get_workflow_execution_tree(
    workflow_id: str = Path(
        ..., description="The workflow id that you want to retrieve"
    ),
    temporal_client: Client = Depends(get_temporal_client),
) -> GetWorkflowExecutionTreeResponse:
    """Gets the lineage of a given workflow using its id."""
    try:
        response = await service.get_workflow_execution_tree(
            workflow_id=workflow_id, temporal_client=temporal_client
        )
        return response
    except Exception as e:
        logger.warn(
            action=EventAction.ACCESS,
            outcome=EventOutcome.FAILURE,
            category=EventCategory.API,
            default_event=LogEventDefault.API_RESPONSE,
            message=f"Error retrieving workflow execution tree: {str(e)}",
        )
        raise HTTPException(
            status_code=500,
            detail="An error occurred during workflow execution tree retrieval",
        )
