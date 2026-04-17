"""Vector upload functions for Qdrant."""

import uuid
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client import models as qm
from qdrant_client.http.models import PointStruct

from src.env import ENV
from src.models.emb_client import EmbeddingClient
from src.workflows.qdrant.schemas import (
    ChunkMetadata,
    ParentChunkMetadata,
    QdrantDocumentContext,
    QuestionMetadata,
    SummaryMetadata,
)


def _chunk_metadata_from_dict(
    chunk_id: str,
    page_content: str,
    metadata: dict[str, Any],
    parent_chunk_id: str | None = None,
) -> ChunkMetadata:
    """Build ChunkMetadata from a raw metadata dict (works for both Chunk and SubChunk)."""
    return ChunkMetadata(
        chunk_id=str(chunk_id),
        page_content=page_content,
        page_numbers=metadata.get("page_numbers", []),
        chunk_type=metadata.get("chunk_type"),
        parent_chunk_id=str(parent_chunk_id) if parent_chunk_id else None,
        # headers / structure
        header_1=metadata.get("Header 1"),
        header_2=metadata.get("Header 2"),
        header_3=metadata.get("Header 3"),
        toc_path=metadata.get("toc_path", []),
        all_subchapters=metadata.get("all_subchapters", []),
        # element metadata
        asset_path=metadata.get("asset_path"),
        caption=metadata.get("caption"),
        summary=metadata.get("summary"),
        description=metadata.get("description"),
        content=metadata.get("content"),
        footnote=metadata.get("footnote"),
        # cross-chunk linking
        related_assets=metadata.get("related_assets", []),
        related_text=metadata.get("related_text", []),
        # enrichment
        focus_topic=metadata.get("focus_topic"),
        wildlife_mentioned=metadata.get("wildlife_mentioned"),
        plant_species_mentioned=metadata.get("plant_species_mentioned"),
        wildlife_species=metadata.get("wildlife_species", []),
        plant_species=metadata.get("plant_species", []),
        map_scale=metadata.get("map_scale"),
        hypothetical_questions=metadata.get("hypothetical_questions", []),
    )


async def _upload_chunks_to_qdrant(
    chunks: list[ChunkMetadata],
    doc_context: QdrantDocumentContext,
    qdrant_client: AsyncQdrantClient,
    avg_document_length: float,
    embedding_client: EmbeddingClient,
) -> None:
    """Upload a batch of chunks to Qdrant with dense + sparse vectors."""
    if not chunks:
        return

    collection_name = ENV.QDRANT_COLLECTION_NAME
    chunk_texts = [chunk.page_content for chunk in chunks]

    chunk_vectors = await embedding_client.aembed_many(chunk_texts)

    points: list[PointStruct] = []
    for chunk, dense_vec in zip(chunks, chunk_vectors, strict=False):
        chunk_payload = chunk.model_dump(exclude={"page_content"})
        payload = {
            "type": "chunk",
            "project_id": doc_context.project_id,
            "document_id": doc_context.document_id,
            "source_file_id": doc_context.source_file_id,
            "title": doc_context.title,
            "chunk_content": chunk.page_content,
            **chunk_payload,
        }

        points.append(
            PointStruct(
                id=chunk.chunk_id,
                vector={
                    "dense": dense_vec,
                    "sparse": qm.Document(
                        text=chunk.page_content,
                        model="Qdrant/bm25",
                        options={"avg_len": avg_document_length},
                    ),
                },
                payload=payload,
            )
        )

    await qdrant_client.upsert(collection_name=collection_name, points=points, wait=True)


async def _upload_questions_to_qdrant(
    questions: list[QuestionMetadata],
    doc_context: QdrantDocumentContext,
    qdrant_client: AsyncQdrantClient,
    avg_question_length: float,
    embedding_client: EmbeddingClient,
) -> None:
    """Upload hypothetical questions to Qdrant with dense + sparse vectors."""
    if not questions:
        return

    collection_name = ENV.QDRANT_COLLECTION_NAME
    texts = [q.question_text for q in questions]

    dense_vectors = await embedding_client.aembed_many(texts)

    points: list[PointStruct] = []
    for question, dense_vec in zip(questions, dense_vectors, strict=False):
        payload = {
            "type": "question",
            "project_id": doc_context.project_id,
            "document_id": doc_context.document_id,
            "source_file_id": doc_context.source_file_id,
            "title": doc_context.title,
            "chunk_id": question.chunk_id,
            "parent_chunk_id": question.parent_chunk_id,
            "question_text": question.question_text,
        }
        points.append(
            PointStruct(
                id=str(uuid.uuid4()),
                vector={
                    "dense": dense_vec,
                    "sparse": qm.Document(
                        text=question.question_text,
                        model="Qdrant/bm25",
                        options={"avg_len": avg_question_length},
                    ),
                },
                payload=payload,
            )
        )

    await qdrant_client.upsert(collection_name=collection_name, points=points, wait=True)


async def _upload_parent_chunks_to_qdrant(
    parent_chunks: list[ParentChunkMetadata],
    doc_context: QdrantDocumentContext,
    qdrant_client: AsyncQdrantClient,
) -> None:
    """Upload parent chunks to Qdrant as payload-only points (no vectors)."""
    if not parent_chunks:
        return

    collection_name = ENV.QDRANT_COLLECTION_NAME

    points: list[PointStruct] = []
    for pc in parent_chunks:
        payload = {
            "type": "parent_chunk",
            "project_id": doc_context.project_id,
            "document_id": doc_context.document_id,
            "source_file_id": doc_context.source_file_id,
            "chunk_id": pc.chunk_id,
            "page_content": pc.page_content,
            "page_numbers": pc.page_numbers,
            "title": doc_context.title,
        }
        points.append(PointStruct(id=pc.chunk_id, vector={}, payload=payload))

    await qdrant_client.upsert(collection_name=collection_name, points=points, wait=True)


async def _upload_summaries_to_qdrant(
    summaries: list[SummaryMetadata],
    doc_context: QdrantDocumentContext,
    qdrant_client: AsyncQdrantClient,
    embedding_client: EmbeddingClient,
) -> None:
    """Upload document summaries to Qdrant with dense + sparse vectors."""
    if not summaries:
        return

    collection_name = ENV.QDRANT_COLLECTION_NAME
    texts = [s.summary_text for s in summaries]

    dense_vectors = await embedding_client.aembed_many(texts)
    avg_document_length = sum(len(t.split()) for t in texts) / len(texts)

    points: list[PointStruct] = []
    for summary, dense_vec in zip(summaries, dense_vectors, strict=False):
        payload = {
            "type": "summary",
            "project_id": doc_context.project_id,
            "document_id": doc_context.document_id,
            "source_file_id": doc_context.source_file_id,
            "title": doc_context.title,
            "summary_text": summary.summary_text,
        }
        points.append(
            PointStruct(
                id=str(uuid.uuid4()),
                vector={
                    "dense": dense_vec,
                    "sparse": qm.Document(
                        text=summary.summary_text,
                        model="Qdrant/bm25",
                        options={"avg_len": avg_document_length},
                    ),
                },
                payload=payload,
            )
        )

    await qdrant_client.upsert(collection_name=collection_name, points=points, wait=True)
