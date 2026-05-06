"""Qdrant client management and collection setup."""

from qdrant_client import AsyncQdrantClient
from qdrant_client import models as qm
from temporalio import activity

from src.env import ENV


def _get_qdrant_client() -> AsyncQdrantClient:
    """Create an AsyncQdrantClient with optional API key authentication."""
    api_key = ENV.QDRANT_API_KEY.get_secret_value() or None
    return AsyncQdrantClient(url=ENV.QDRANT_BASE_URL, port=None, api_key=api_key)


@activity.defn(name="init_qdrant_collection")
async def _init_qdrant_collection() -> None:
    """Initialise the shared Qdrant collection (idempotent).

    Creates a single multitenant collection with per-tenant HNSW indexing
    (global HNSW disabled via m=0, per-tenant via payload_m=16).
    The project_id field is marked as tenant key for optimal partitioning.
    """
    col_name = ENV.QDRANT_COLLECTION_NAME
    client = AsyncQdrantClient(url=ENV.QDRANT_BASE_URL, port=None, api_key=ENV.QDRANT_API_KEY or None)
    try:
        if await client.collection_exists(col_name):
            activity.logger.info("Collection already exists: %s", col_name)
            return

        await client.create_collection(
            collection_name=col_name,
            vectors_config={
                "dense": qm.VectorParams(
                    size=ENV.QDRANT_DENSE_VECTOR_SIZE,
                    distance=qm.Distance.COSINE,
                )
            },
            sparse_vectors_config={"sparse": qm.SparseVectorParams(modifier=qm.Modifier.IDF)},
            hnsw_config=qm.HnswConfigDiff(payload_m=16, m=0),
        )

        # Tenant index — enables per-tenant HNSW and optimised segment grouping
        await client.create_payload_index(
            col_name,
            "project_id",
            field_schema=qm.KeywordIndexParams(
                type=qm.KeywordIndexType.KEYWORD,
                is_tenant=True,
            ),
        )

        # Payload indices (union of all point types)
        schema: dict[str, list[str]] = {
            "keywords": [
                "type",
                "document_id",
                "source_file_id",
                "chunk_id",
                "previous_chunk_id",
                "next_chunk_id",
                "chunk_type",
                "parent_chunk_id",
                "focus_topic",
                "map_scale",
                "asset_path",
            ],
            "text": [
                "title",
                "chunk_content",
                "question_text",
                "summary_text",
                "page_content",
                "header_1",
                "header_2",
                "header_3",
                "caption",
                "description",
                "summary",
            ],
            "integers": ["page_numbers"],
            "booleans": ["wildlife_mentioned", "plant_species_mentioned"],
        }

        for field in schema.get("keywords", []):
            await client.create_payload_index(col_name, field, qm.PayloadSchemaType.KEYWORD)
        for field in schema.get("text", []):
            await client.create_payload_index(col_name, field, qm.PayloadSchemaType.TEXT)
        for field in schema.get("integers", []):
            await client.create_payload_index(col_name, field, qm.PayloadSchemaType.INTEGER)
        for field in schema.get("booleans", []):
            await client.create_payload_index(col_name, field, qm.PayloadSchemaType.BOOL)

        activity.logger.info("Created multitenant collection with indices: %s", col_name)
    finally:
        await client.close()


async def init_qdrant_collection() -> None:
    """Workflow wrapper: idempotent Qdrant collection init."""
    from datetime import timedelta

    from temporalio import workflow
    from temporalio.common import RetryPolicy

    from src.config import get_config

    await workflow.execute_activity(
        _init_qdrant_collection,
        start_to_close_timeout=timedelta(seconds=60),
        retry_policy=RetryPolicy(
            maximum_attempts=get_config().TEMPORAL_QDRANT_ACTIVITY_MAX_ATTEMPTS,
            non_retryable_error_types=["ValueError"],
            initial_interval=timedelta(seconds=5),
            backoff_coefficient=2,
            maximum_interval=timedelta(seconds=60),
        ),
    )
