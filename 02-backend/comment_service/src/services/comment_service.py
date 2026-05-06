from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from event_logging.enums import (
    EventAction,
    EventCategory,
    EventOutcome,
    LogEventDefault,
)
from src.exceptions.exceptions import NotFoundError
from src.models.db.enums import ProcessStep, SourceType
from src.models.db_models import Comment
from src.models.schemas.comment_schemas import (
    CommentResponse,
    CreateCommentRequest,
    SourceRef,
    UpdateCommentRequest,
)
from src.utils.logger import logger

def _decompose_source_ref(data: dict[str, Any], source_ref: SourceRef | None) -> None:
    """Extract source_ref into flat source_type/source_item_id columns."""
    data["source_type"] = source_ref.type if source_ref is not None else None
    data["source_item_id"] = source_ref.item_id if source_ref is not None else None


def _to_comment_response(comment: Comment) -> CommentResponse:
    """Map DB row shape to API response contract."""
    source_ref: SourceRef | None = None
    if comment.source_type is not None:
        if comment.source_type == SourceType.MANUAL or comment.source_item_id:
            source_ref = SourceRef(
                type=comment.source_type,
                item_id=comment.source_item_id,
            )
        else:
            logger.warn(
                EventAction.VALIDATE,
                EventOutcome.FAILURE,
                EventCategory.DATABASE,
                default_event=LogEventDefault.VALIDATION_FAILURE,
                message=(
                    "Detected inconsistent source reference on comment id="
                    f"{comment.id}; returning source_ref as null"
                ),
            )
    return CommentResponse(
        id=comment.id,
        project_id=comment.project_id,
        title=comment.title,
        content=comment.content,
        process_step=comment.process_step,
        source_ref=source_ref,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
    )


async def get_comments(
    project_id: UUID,
    db: AsyncSession,
    process_steps: list[ProcessStep] | None = None,
    source_types: list[SourceType] | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> list[CommentResponse]:
    logger.info(
        EventAction.READ,
        EventOutcome.UNKNOWN,
        EventCategory.DATABASE,
        default_event=LogEventDefault.DB_READ,
        message=f"Fetching comments for project_id={project_id}",
    )
    query = select(Comment).where(Comment.project_id == project_id)

    if process_steps:
        query = query.where(Comment.process_step.in_(process_steps))
    if source_types:
        query = query.where(Comment.source_type.in_(source_types))

    query = query.order_by(Comment.created_at.asc())

    if offset is not None:
        query = query.offset(offset)
    if limit is not None:
        query = query.limit(limit)

    result = await db.execute(query)
    comments = list(result.scalars().all())
    logger.info(
        EventAction.READ,
        EventOutcome.SUCCESS,
        EventCategory.DATABASE,
        default_event=LogEventDefault.DB_SUCCESS,
        message=f"Retrieved {len(comments)} comments for project_id={project_id}",
    )
    return [_to_comment_response(comment) for comment in comments]


async def create_comment(
    project_id: UUID, payload: CreateCommentRequest, db: AsyncSession
) -> CommentResponse:
    logger.info(
        EventAction.WRITE,
        EventOutcome.UNKNOWN,
        EventCategory.DATABASE,
        default_event=LogEventDefault.DB_WRITE,
        message=f"Creating comment for project_id={project_id}, process_step={payload.process_step}",
    )
    comment_dict = payload.model_dump(exclude={"source_ref"})
    comment_dict["project_id"] = project_id
    _decompose_source_ref(comment_dict, payload.source_ref)

    comment = Comment(**comment_dict)
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    logger.info(
        EventAction.WRITE,
        EventOutcome.SUCCESS,
        EventCategory.DATABASE,
        default_event=LogEventDefault.DB_SUCCESS,
        message=f"Created comment id={comment.id} for project_id={project_id}",
    )
    return _to_comment_response(comment)


async def update_comment(
    project_id: UUID, comment_id: UUID, payload: UpdateCommentRequest, db: AsyncSession
) -> CommentResponse:
    query = select(Comment).where(
        Comment.id == comment_id, Comment.project_id == project_id
    )
    result = await db.execute(query)
    comment = result.scalar_one_or_none()

    if not comment:
        raise NotFoundError(f"Comment {comment_id} not found")

    logger.info(
        EventAction.CHANGE,
        EventOutcome.UNKNOWN,
        EventCategory.DATABASE,
        default_event=LogEventDefault.DB_WRITE,
        message=f"Updating comment id={comment_id} for project_id={project_id}",
    )

    update_dict = payload.model_dump(exclude_unset=True, exclude={"source_ref"})
    if "source_ref" in payload.model_fields_set:
        _decompose_source_ref(update_dict, payload.source_ref)

    if not update_dict:
        return _to_comment_response(comment)

    for field, value in update_dict.items():
        setattr(comment, field, value)

    await db.commit()
    await db.refresh(comment)
    logger.info(
        EventAction.CHANGE,
        EventOutcome.SUCCESS,
        EventCategory.DATABASE,
        default_event=LogEventDefault.DB_SUCCESS,
        message=f"Updated comment id={comment_id} for project_id={project_id}",
    )
    return _to_comment_response(comment)


async def delete_comment(
    project_id: UUID, comment_id: UUID, db: AsyncSession
) -> None:
    query = select(Comment).where(
        Comment.id == comment_id, Comment.project_id == project_id
    )
    result = await db.execute(query)
    comment = result.scalar_one_or_none()

    if not comment:
        raise NotFoundError(f"Comment {comment_id} not found")

    await db.delete(comment)
    await db.commit()

    logger.info(
        EventAction.DELETE,
        EventOutcome.SUCCESS,
        EventCategory.DATABASE,
        default_event=LogEventDefault.DB_SUCCESS,
        message=f"Deleted comment id={comment_id} for project_id={project_id}",
    )
