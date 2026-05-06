"""Temporal activities for Qdrant database operations."""

from qdrant_client.models import PointStruct
from temporalio import activity, workflow

from src.config.config import Config, config
from src.qdrant.schemas import ChunkPayload

with workflow.unsafe.imports_passed_through():
    from src.workflows.qdrant_wf.schemas.workflow import (
        DocumentActivityInput,
        EmbedAndUploadInput,
    )

from src.workflows.clients import embedding_client, qdrant_client


@activity.defn
async def init_qdrant_collection() -> None:
    """Initializes claim Qdrant collection for claims if it doesn't exist."""
    qdrant_client.init_claim_collection()


@activity.defn
async def delete_document_from_qdrant(inp: DocumentActivityInput) -> None:
    """Deletes all entries for a specific document from the claims collection."""
    qdrant_client.clear_document_claims(project_id=inp.project_id, document_id=inp.document_id)


@activity.defn
async def fetch_and_prepare_chunks(inp: DocumentActivityInput) -> list[ChunkPayload]:
    """Retrieves and prepares chunk metadata from Qdrant for a list of point IDs.

    Fetches raw chunk data from the project's 'chunks' collection using
    provided point IDs. Filters out invalid chunks (short content or image type)
    and maps the results to a structured metadata format.

    Args:
        inp: DocumentActivityInput containing project_id and document_id.

    Returns:
        List of valid ChunkPayloads.
    """
    chunk_ids = qdrant_client.get_chunk_ids_by_document_id(project_id=inp.project_id, document_id=inp.document_id)

    chunk_payloads = qdrant_client.get_chunk_payloads(project_id=inp.project_id, chunk_ids=chunk_ids)

    valid_chunks = [
        c
        for c in chunk_payloads
        if len(c.chunk_content) >= Config.QDRANT_BUILDER.CHUNK_MIN_LENGTH and c.chunk_type != "image"
    ]

    return valid_chunks


@activity.defn
async def embed_and_upload_claims(inp: EmbedAndUploadInput) -> None:
    """Embed claims and upload to Qdrant."""
    if not inp.claims:
        return

    texts = [c.claim_text for c in inp.claims]
    emb_matrix = await embedding_client.aembed_many(texts)
    for claim, emb in zip(inp.claims, emb_matrix, strict=True):
        claim.vector = emb
    collection_name = Config.QDRANT.CLAIM_COLLECTION_NAME

    points = [
        PointStruct(
            id=c.claim_id,
            vector=c.vector,
            payload={
                "project_id": c.project_id,
                "document_id": c.document_id,
                "title": c.title,
                "chunk_id": c.chunk_id,
                "erlauterungsbericht": c.erlauterungsbericht,
                "claim_metadata": {
                    "claim_id": c.claim_id,
                    "claim_content": c.claim_text,
                    "evidence": c.claim_metadata.evidence,
                },
            },
        )
        for c in inp.claims
    ]

    batch_size = config.QDRANT_BUILDER.PROCESS_AND_UPLOAD_BATCH_SIZE
    for i in range(0, len(points), batch_size):
        qdrant_client.upsert(collection_name=collection_name, points=points[i : i + batch_size], wait=True)

    activity.logger.info(f"Uploaded {len(inp.claims)} claims for doc {inp.claims[0].document_id} to Qdrant.")


@activity.defn
async def get_claim_ids(inp: DocumentActivityInput) -> list[str]:
    """Retrieves all claim IDs for a given document from Qdrant."""
    return qdrant_client.get_claim_ids(inp.document_id, inp.project_id)
