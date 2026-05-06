"""Temporal activities for document indexing and listing."""

import json
import uuid
from datetime import timedelta

from pydantic import BaseModel
from qdrant_client import AsyncQdrantClient
from qdrant_client import models as qm
from temporalio import activity, workflow
from temporalio.common import RetryPolicy

from src.config import get_config
from src.env import ENV
from src.models.emb_client import EmbeddingClient
from src.schemas import ProcessedDocument
from src.utils.dms_utils import (
    ListFilesInput,
    download_file,
    list_files,
)
from src.workflows.qdrant.schemas import (
    ChunkMetadata,
    ParentChunkMetadata,
    QdrantDocumentContext,
    QuestionMetadata,
    SummaryMetadata,
)

from .upload import (
    _chunk_metadata_from_dict,
    _upload_chunks_to_qdrant,
    _upload_parent_chunks_to_qdrant,
    _upload_questions_to_qdrant,
    _upload_summaries_to_qdrant,
)

# ---------------------------------------------------------------------------
# Activity I/O models
# ---------------------------------------------------------------------------


class QdrantExtractionFile(BaseModel):
    """A _processed.json file found in DMS."""

    extraction_file_id: str  # DMS file_id of the _processed.json
    filename: str
    project_id: str


class QdrantDocumentInput(BaseModel):
    """Input for the index_document_to_qdrant activity."""

    extraction_file_id: str  # DMS file_id of _processed.json
    project_id: str


# ---------------------------------------------------------------------------
# Activity implementations
# ---------------------------------------------------------------------------


@activity.defn(name="get_inhalts_extraktion_docs")
async def _get_inhalts_extraktion_docs(project_id: str) -> list[QdrantExtractionFile]:
    """List all _processed.json files for a project from DMS.

    Paginates through all pages to ensure no files are missed.
    """
    proj_uuid = uuid.UUID(project_id)
    page_size = 500
    page = 1
    results: list[QdrantExtractionFile] = []
    total_files = 0

    while True:
        batch = await list_files(
            ListFilesInput(
                project_id=proj_uuid,
                file_type="content_extraction",
                page=page,
                page_size=page_size,
            )
        )
        total_files += len(batch)

        for f in batch:
            if f.filename.endswith("_processed.json"):
                results.append(
                    QdrantExtractionFile(
                        extraction_file_id=str(f.id),
                        filename=f.filename,
                        project_id=project_id,
                    )
                )

        if len(batch) < page_size:
            break
        page += 1

    activity.logger.info(
        "Found %d _processed.json files across %d total content_extraction files (%d pages) for project %s",
        len(results),
        total_files,
        page,
        project_id,
    )
    return results


@activity.defn(name="index_document_to_qdrant")
async def _index_document_to_qdrant(input: QdrantDocumentInput) -> str:  # noqa: C901
    """Download a processed document from DMS and index it into Qdrant.

    Embeds and upserts chunks, hypothetical questions, parent chunks, and
    document summaries into the shared multitenant collection.
    Emits heartbeats after each batch so Temporal can detect liveness.
    """
    cfg = get_config()

    # Download the _processed.json from DMS
    raw_bytes = await download_file(input.extraction_file_id)
    data = json.loads(raw_bytes)
    processed_doc = ProcessedDocument(**data)

    document_id = input.extraction_file_id
    document_name = processed_doc.metadata.original_document_name

    activity.logger.info(
        "Processing document %s (%s) — %d chunks",
        document_id,
        document_name,
        len(processed_doc.chunks),
    )

    # Flatten chunks: use sub_chunks if present, otherwise use the parent chunk itself
    prepared_chunks: list[ChunkMetadata] = []
    for chunk in processed_doc.chunks:
        if chunk.sub_chunks:
            for sub in chunk.sub_chunks:
                prepared_chunks.append(
                    _chunk_metadata_from_dict(
                        chunk_id=str(sub.chunk_id),
                        page_content=sub.page_content,
                        metadata=sub.metadata,
                        parent_chunk_id=str(sub.parent_chunk_id) if sub.parent_chunk_id else None,
                    )
                )
        else:
            # Parent chunk with no sub_chunks — index it directly
            prepared_chunks.append(
                _chunk_metadata_from_dict(
                    chunk_id=str(chunk.chunk_id),
                    page_content=chunk.page_content,
                    metadata=chunk.metadata,
                )
            )

    # Set prev/next pointers in a second pass
    for i, cm in enumerate(prepared_chunks):
        cm.previous_chunk_id = prepared_chunks[i - 1].chunk_id if i > 0 else None
        cm.next_chunk_id = prepared_chunks[i + 1].chunk_id if i < len(prepared_chunks) - 1 else None

    # Extract hypothetical questions from parent chunks (not sub_chunks to avoid duplication)
    prepared_questions: list[QuestionMetadata] = []
    for chunk in processed_doc.chunks:
        questions = chunk.metadata.get("hypothetical_questions", [])
        for q_text in questions:
            if not q_text.strip():
                continue
            prepared_questions.append(
                QuestionMetadata(
                    question_text=q_text.strip(),
                    chunk_id=str(chunk.chunk_id),
                    parent_chunk_id=None,  # this IS the parent
                )
            )

    # Extract parent chunks (only those that actually have sub_chunks)
    prepared_parent_chunks: list[ParentChunkMetadata] = []
    for chunk in processed_doc.chunks:
        if chunk.sub_chunks:
            prepared_parent_chunks.append(
                ParentChunkMetadata(
                    chunk_id=str(chunk.chunk_id),
                    page_content=chunk.page_content,
                    page_numbers=chunk.metadata.get("page_numbers", []),
                )
            )

    # Extract document summary
    prepared_summaries: list[SummaryMetadata] = []
    if processed_doc.metadata.summary:
        prepared_summaries.append(SummaryMetadata(summary_text=processed_doc.metadata.summary))

    if not prepared_chunks:
        activity.logger.info("No sub-chunks found for document %s — skipping.", document_id)
        return document_id

    doc_context = QdrantDocumentContext(
        project_id=input.project_id,
        document_id=document_id,
        source_file_id=processed_doc.metadata.source_file_id,
        title=document_name,
    )

    # Compute avg document length once for BM25 params
    all_texts = [c.page_content for c in prepared_chunks]
    avg_document_length = sum(len(t.split()) for t in all_texts) / len(all_texts)

    batch_size = cfg.QDRANT_UPLOAD_BATCH_SIZE
    collection_name = ENV.QDRANT_COLLECTION_NAME

    embedding_client = EmbeddingClient()
    qdrant_client = AsyncQdrantClient(url=ENV.QDRANT_BASE_URL, port=None, api_key=ENV.QDRANT_API_KEY or None)
    try:
        # Delete existing points for this document (all types in one call)
        doc_filter = qm.FilterSelector(
            filter=qm.Filter(
                must=[
                    qm.FieldCondition(
                        key="project_id",
                        match=qm.MatchValue(value=doc_context.project_id),
                    ),
                    qm.FieldCondition(
                        key="document_id",
                        match=qm.MatchValue(value=doc_context.document_id),
                    ),
                ]
            )
        )
        await qdrant_client.delete(collection_name=collection_name, points_selector=doc_filter)

        # 1. Upload chunks (batched with heartbeats)
        for i in range(0, len(prepared_chunks), batch_size):
            batch = prepared_chunks[i : i + batch_size]
            await _upload_chunks_to_qdrant(
                chunks=batch,
                doc_context=doc_context,
                qdrant_client=qdrant_client,
                avg_document_length=avg_document_length,
                embedding_client=embedding_client,
            )
            activity.heartbeat(f"Uploaded chunk batch {i // batch_size + 1}")

        # 2. Upload questions (batched with heartbeats)
        if prepared_questions:
            q_texts = [q.question_text for q in prepared_questions]
            avg_question_length = sum(len(t.split()) for t in q_texts) / len(q_texts)
            for i in range(0, len(prepared_questions), batch_size):
                batch = prepared_questions[i : i + batch_size]
                await _upload_questions_to_qdrant(
                    questions=batch,
                    doc_context=doc_context,
                    qdrant_client=qdrant_client,
                    avg_question_length=avg_question_length,
                    embedding_client=embedding_client,
                )
                activity.heartbeat(f"Uploaded question batch {i // batch_size + 1}")

        # 3. Upload parent chunks (batched with heartbeats, no embeddings)
        if prepared_parent_chunks:
            for i in range(0, len(prepared_parent_chunks), batch_size):
                batch = prepared_parent_chunks[i : i + batch_size]
                await _upload_parent_chunks_to_qdrant(
                    parent_chunks=batch,
                    doc_context=doc_context,
                    qdrant_client=qdrant_client,
                )
                activity.heartbeat(f"Uploaded parent chunk batch {i // batch_size + 1}")

        # 4. Upload summaries (typically a single point per document)
        if prepared_summaries:
            await _upload_summaries_to_qdrant(
                summaries=prepared_summaries,
                doc_context=doc_context,
                qdrant_client=qdrant_client,
                embedding_client=embedding_client,
            )
            activity.heartbeat("Uploaded summaries")
    finally:
        await qdrant_client.close()
        await embedding_client.close()

    activity.logger.info(
        "Uploaded %d chunks, %d questions, %d parent chunks, %d summaries for document %s to Qdrant.",
        len(prepared_chunks),
        len(prepared_questions),
        len(prepared_parent_chunks),
        len(prepared_summaries),
        document_id,
    )
    return document_id


# ---------------------------------------------------------------------------
# Workflow wrapper functions
# ---------------------------------------------------------------------------


async def get_inhalts_extraktion_docs(project_id: str) -> list[QdrantExtractionFile]:
    """Workflow wrapper: fetch DMS extraction file list."""
    return await workflow.execute_activity(
        _get_inhalts_extraktion_docs,
        project_id,
        start_to_close_timeout=timedelta(minutes=2),
        retry_policy=RetryPolicy(
            maximum_attempts=get_config().TEMPORAL_QDRANT_ACTIVITY_MAX_ATTEMPTS,
            non_retryable_error_types=["ValueError"],
            initial_interval=timedelta(seconds=5),
            backoff_coefficient=2,
            maximum_interval=timedelta(seconds=60),
        ),
    )


async def index_document_to_qdrant(input: QdrantDocumentInput) -> str:
    """Workflow wrapper: index a single document into Qdrant."""
    return await workflow.execute_activity(
        _index_document_to_qdrant,
        input,
        start_to_close_timeout=timedelta(minutes=30),
        heartbeat_timeout=timedelta(minutes=5),
        retry_policy=RetryPolicy(
            maximum_attempts=get_config().TEMPORAL_QDRANT_ACTIVITY_MAX_ATTEMPTS,
            non_retryable_error_types=["ValueError", "RuntimeError"],
            initial_interval=timedelta(seconds=10),
            backoff_coefficient=2,
            maximum_interval=timedelta(seconds=60),
        ),
    )
