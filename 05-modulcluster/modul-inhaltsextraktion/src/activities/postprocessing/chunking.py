# src/activities/postprocessing/chunking.py
"""
Temporal activities for markdown chunking and page splitting.
"""

from datetime import timedelta

from pydantic import BaseModel
from temporalio import activity, workflow
from temporalio.common import RetryPolicy

from src.config import get_config
from src.processors.chunker import MarkdownChunker
from src.providers.base import ContentItemDict
from src.schemas import Chunk
from src.utils.text_utils import split_markdown_by_pages as _split_markdown_impl


class ChunkMarkdownInput(BaseModel):
    """Input for chunk_markdown activity."""

    markdown: str
    content_list: list[ContentItemDict]


class SplitMarkdownByPagesInput(BaseModel):
    """Input for split_markdown_by_pages activity."""

    markdown: str
    pages_per_chunk: int = 1


@activity.defn(name="chunk_markdown")
async def _chunk_markdown(input: ChunkMarkdownInput) -> list[Chunk]:
    """Chunks markdown content into hierarchical chunks."""
    activity.heartbeat("Starting chunking")
    result = MarkdownChunker.chunk_markdown(input.markdown, input.content_list)
    activity.heartbeat(f"Chunking complete: {len(result)} chunks")
    return result


@activity.defn(name="split_markdown_by_pages")
async def _split_markdown_by_pages(input: SplitMarkdownByPagesInput) -> list[str]:
    """Splits markdown content by page markers into chunks."""
    return _split_markdown_impl(input.markdown, input.pages_per_chunk)


# --- Workflow wrappers ---


async def chunk_markdown(
    markdown: str,
    content_list: list[ContentItemDict],
) -> list[Chunk]:
    """Workflow wrapper for chunk_markdown activity."""
    return await workflow.execute_activity(
        _chunk_markdown,
        ChunkMarkdownInput(markdown=markdown, content_list=content_list),
        start_to_close_timeout=timedelta(minutes=10),
        heartbeat_timeout=timedelta(minutes=3),
        retry_policy=RetryPolicy(maximum_attempts=get_config().TEMPORAL_PROCESSING_ACTIVITY_MAX_ATTEMPTS),
    )


async def split_markdown_by_pages(
    markdown: str,
    pages_per_chunk: int = 1,
) -> list[str]:
    """Workflow wrapper for split_markdown_by_pages activity."""
    return await workflow.execute_activity(
        _split_markdown_by_pages,
        SplitMarkdownByPagesInput(markdown=markdown, pages_per_chunk=pages_per_chunk),
        start_to_close_timeout=timedelta(minutes=5),
        retry_policy=RetryPolicy(maximum_attempts=get_config().TEMPORAL_PROCESSING_ACTIVITY_MAX_ATTEMPTS),
    )
