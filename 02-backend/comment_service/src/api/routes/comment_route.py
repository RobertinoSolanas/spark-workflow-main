from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.database import get_db_session
from src.models.db.enums import ProcessStep, SourceType
from src.models.schemas.comment_schemas import (
    CommentResponse,
    CreateCommentRequest,
    UpdateCommentRequest,
)
from src.services import comment_service

router = APIRouter(prefix="/projects", tags=["Comments"])


@router.get("/{project_id}/comments", response_model=list[CommentResponse])
async def get_comments(
    project_id: UUID,
    process_step: list[ProcessStep] | None = Query(None),
    source_type: list[SourceType] | None = Query(None),
    limit: int | None = Query(None, ge=1, le=100),
    offset: int | None = Query(None, ge=0),
    db: AsyncSession = Depends(get_db_session),
) -> list[CommentResponse]:
    return await comment_service.get_comments(
        project_id, db, process_step, source_type, limit, offset
    )


@router.post(
    "/{project_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_comment(
    project_id: UUID,
    payload: CreateCommentRequest,
    db: AsyncSession = Depends(get_db_session),
) -> CommentResponse:
    return await comment_service.create_comment(project_id, payload, db)


@router.patch("/{project_id}/comments/{comment_id}", response_model=CommentResponse)
async def update_comment(
    project_id: UUID,
    comment_id: UUID,
    payload: UpdateCommentRequest,
    db: AsyncSession = Depends(get_db_session),
) -> CommentResponse:
    return await comment_service.update_comment(project_id, comment_id, payload, db)


@router.delete(
    "/{project_id}/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_comment(
    project_id: UUID,
    comment_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> None:
    await comment_service.delete_comment(project_id, comment_id, db)
