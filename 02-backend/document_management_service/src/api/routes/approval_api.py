from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from src.models.db.workflow_enum import ApprovalStatus
from src.models.schemas.approval_schema import (
    ApprovalActionResponse,
    CancelResponse,
    FileDiffResponse,
)
from src.services.temporal.temporal_service import TemporalWorkflowService
from src.utils.service_utils import get_or_create_temporal_workflow_service

router = APIRouter(prefix="/v2/files", tags=["File Approval"])


@router.get(
    "/{file_id}/approval-status",
    response_model=ApprovalStatus,
    summary="Get current approval status of a workflow",
    description=(
        "Queries the Temporal workflow to check if it's pending approval, approved,"
        " rejected, etc."
    ),
)
async def get_file_approval_status(
    file_id: UUID,
    service: TemporalWorkflowService = Depends(get_or_create_temporal_workflow_service),
):
    """
    Returns the current approval status.

    Useful for frontend polling while waiting for user decision.
    """
    approval_status = await service.get_approval_status(str(file_id))
    return approval_status


@router.post(
    "/{file_id}/decision",
    response_model=ApprovalActionResponse,
)
async def submit_approval(
    file_id: UUID,
    decision: Literal["approve", "reject"],
    service: TemporalWorkflowService = Depends(get_or_create_temporal_workflow_service),
):
    """
    Single endpoint for both approve & reject actions.
    Useful for simpler frontend forms.
    """
    if decision == "approve":
        await service.approve_workflow(str(file_id))
    elif decision == "reject":
        await service.reject_workflow(str(file_id))
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Decision must be 'approve' or 'reject'",
        )

    approval_status = await service.get_approval_status(str(file_id))
    return ApprovalActionResponse(
        status="success",
        message=f"Workflow for file {file_id}: {decision}",
        current_approval_status=approval_status,
    )


@router.get(
    "/{file_id}/diff",
    response_model=FileDiffResponse,
    summary="Get the diff of the project files",
    description=(
        "Takes the uploaded file or files and creates a diff to current project files."
    ),
)
async def get_file_diff(
    file_id: UUID,
    service: TemporalWorkflowService = Depends(get_or_create_temporal_workflow_service),
):
    """
    Returns the current file diff of the project files.
    """
    file_diff = await service.get_file_diff(str(file_id))
    return file_diff


@router.post(
    "/{file_id}/diff",
    response_model=FileDiffResponse,
    summary="Set the diff of the project files",
    description="Can be used to modify a diff to current project files.",
)
async def set_file_diff(
    file_id: UUID,
    diff: FileDiffResponse,
    service: TemporalWorkflowService = Depends(get_or_create_temporal_workflow_service),
):
    """
    Sets the diff of the project files.
    """
    file_diff = await service.set_file_diff(workflow_id=str(file_id), diff=diff)
    return file_diff


@router.get(
    "/{file_id}/cancel",
    summary="Cancel an upload process",
)
async def cancel_upload_process(
    file_id: UUID,
    service: TemporalWorkflowService = Depends(get_or_create_temporal_workflow_service),
):
    """
    Cancel a running upload process.
    """
    await service.cancel_workflow(str(file_id))
    return CancelResponse(file_id=file_id, success=True)
