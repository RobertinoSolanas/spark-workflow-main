from collections.abc import Callable
from typing import Any, Literal, TypeVar

from qdrant_client import QdrantClient, models
from temporalio import activity
from temporalio.exceptions import ApplicationError

from src.config.config import Config
from src.config.env import ENV
from src.qdrant.schemas import (
    ChunkPayload,
    ClaimPayload,
    ParentChunkPayload,
)

TPayload = TypeVar("TPayload", ChunkPayload, ClaimPayload, ParentChunkPayload)


class PlausibilityQdrantClient(QdrantClient):
    def __init__(
        self,
    ) -> None:
        super().__init__(url=ENV.QDRANT.CLUSTER_ENDPOINT, port=None)

    def _get_collection_name(
        self,
        project_id: str,
        collection_type: Literal["claims", "chunks", "parent_chunks"],
    ) -> str:
        if collection_type == "claims":
            return Config.QDRANT.CLAIM_COLLECTION_NAME
        if collection_type in ["chunks", "parent_chunks"]:
            return Config.QDRANT.DATA_COLLECTION_NAME
        raise ValueError(f"Unknown collection type: {collection_type}")

    def get_collection_must_conditions(
        self,
        project_id: str,
        collection_type: Literal["claims", "chunks", "parent_chunks"],
    ) -> list[models.Condition]:
        if collection_type == "claims":
            return [
                models.FieldCondition(
                    key="project_id",
                    match=models.MatchValue(value=project_id),
                )
            ]
        elif collection_type in ["chunks", "parent_chunks"]:
            must_conditions: list[models.Condition] = [
                models.FieldCondition(
                    key="project_id",
                    match=models.MatchValue(value=project_id),
                ),
            ]
            if collection_type == "chunks":
                must_conditions.append(
                    models.FieldCondition(
                        key="type",
                        match=models.MatchValue(value="chunk"),
                    )
                )
            elif collection_type == "parent_chunks":
                must_conditions.append(
                    models.FieldCondition(
                        key="type",
                        match=models.MatchValue(value="parent_chunk"),
                    )
                )
            return must_conditions
        else:
            raise ValueError(f"Unknown collection type: {collection_type}")

    def _get_record_ids(
        self,
        collection_name: str,
        collection_filter: models.Filter,
    ) -> list[str]:
        seen: set[str] = set()
        ordered_ids: list[str] = []

        offset = None
        while True:
            response, offset = self.scroll(
                collection_name=collection_name,
                scroll_filter=collection_filter,
                limit=1000,
                offset=offset,
                with_payload=False,
                with_vectors=False,
            )

            for record in response:
                record_id = str(record.id)
                if record_id not in seen:
                    seen.add(record_id)
                    ordered_ids.append(record_id)

            if offset is None:
                break

        return ordered_ids

    def _get_record_payloads(
        self,
        project_id: str,
        point_ids: list[str],
        collection: Literal["claims", "chunks", "parent_chunks"],
        with_vectors: bool = False,
    ) -> list[Any]:
        collection_name = self._get_collection_name(project_id, collection)

        unique_ids = list(set(point_ids))

        return self.retrieve(
            collection_name=collection_name,
            ids=unique_ids,
            with_payload=True,
            with_vectors=with_vectors,
        )

    def _build_knn_filter(
        self,
        claim_id: str,
        claim_payload: "ClaimPayload",
        chunk_payload: "ChunkPayload | None",
        same_doc_claims_only: bool,
        erlaeuterungsbericht_claims_only: bool,
        exclude_local_claims: bool,
        exclude_claim_ids: list[str] | None,
    ) -> models.Filter:
        """Build a Qdrant filter for KNN claim queries."""
        must_conditions: list[models.Condition] = []
        must_not_conditions: list[models.Condition] = []

        excluded = [claim_id] + (exclude_claim_ids or [])
        must_not_conditions.append(models.HasIdCondition(has_id=excluded))

        if exclude_local_claims and chunk_payload is not None:
            local_chunk_ids = [
                chunk_payload.chunk_id,
                chunk_payload.previous_chunk_id,
                chunk_payload.next_chunk_id,
            ]
            local_chunk_ids = [chunk_id for chunk_id in local_chunk_ids if chunk_id is not None]
            if local_chunk_ids:
                must_not_conditions.append(
                    models.FieldCondition(
                        key="chunk_id",
                        match=models.MatchAny(any=local_chunk_ids),
                    )
                )

        if same_doc_claims_only:
            must_conditions.append(
                models.FieldCondition(
                    key="document_id",
                    match=models.MatchValue(value=claim_payload.document_id),
                )
            )

        if erlaeuterungsbericht_claims_only:
            must_conditions.append(
                models.FieldCondition(
                    key="erlauterungsbericht",
                    match=models.MatchValue(value=True),
                )
            )

        return models.Filter(must=must_conditions, must_not=must_not_conditions)

    def init_claim_collection(self) -> None:
        """Initialize Qdrant collection for claims with the appropriate schema."""
        # Collection creation is idempotent, so this is safe to call multiple times
        if self.collection_exists(collection_name=Config.QDRANT.CLAIM_COLLECTION_NAME):
            return

        collection_name = Config.QDRANT.CLAIM_COLLECTION_NAME

        self.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(size=ENV.QDRANT.VECTOR_SIZE, distance=models.Distance.COSINE),
        )

        for keyword_field in Config.QDRANT.INDEX_KEYWORDS:
            self.create_payload_index(
                collection_name=collection_name, field_name=keyword_field, field_schema=models.PayloadSchemaType.KEYWORD
            )
        for text_field in Config.QDRANT.INDEX_TEXT:
            self.create_payload_index(
                collection_name=collection_name, field_name=text_field, field_schema=models.PayloadSchemaType.TEXT
            )
        for bool_field in Config.QDRANT.INDEX_BOOLS:
            self.create_payload_index(
                collection_name=collection_name, field_name=bool_field, field_schema=models.PayloadSchemaType.BOOL
            )

    def clear_document_claims(self, project_id: str, document_id: str) -> None:
        """Delete all claims associated with a specific document ID."""
        collection_name = Config.QDRANT.CLAIM_COLLECTION_NAME

        if not self.collection_exists(collection_name=collection_name):
            return

        self.delete(
            collection_name=collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=document_id),
                        ),
                        models.FieldCondition(
                            key="project_id",
                            match=models.MatchValue(value=project_id),
                        ),
                    ]
                )
            ),
        )

    def get_claim_knn_ids_all_claims_batched(
        self,
        project_id: str,
        claim_payloads: list["ClaimPayload"],
        chunk_payloads_by_id: dict[str, "ChunkPayload"],
        queries_per_claim: list[dict[str, Any]],
        batch_size: int = 50,
        score_lower_threshold: float = 0.5,
        score_upper_threshold: float = 0.95,
    ) -> list[list[list[str]]]:
        """Issue KNN queries for all claims in configurable-size batches.

        For each claim, the same set of query specs (``queries_per_claim``) is applied.
        All (claim × query) combinations are flattened into a single list of
        ``QueryRequest`` objects, then sent to Qdrant in slices of ``batch_size``.

        Returns a nested list indexed as ``[claim_index][query_index]``, each entry
        being the list of matching claim IDs for that (claim, query) combination.
        """
        collection_name = self._get_collection_name(project_id, "claims")
        n_queries = len(queries_per_claim)

        # Build flat list of (claim_payload, query_spec) pairs in (claim, query) order.
        flat_requests: list[models.QueryRequest] = []
        for claim_payload in claim_payloads:
            chunk_payload = chunk_payloads_by_id.get(claim_payload.chunk_id)
            for q in queries_per_claim:
                flat_requests.append(
                    models.QueryRequest(
                        query=claim_payload.vector,
                        filter=self._build_knn_filter(
                            claim_id=claim_payload.claim_id,
                            claim_payload=claim_payload,
                            chunk_payload=chunk_payload,
                            same_doc_claims_only=q.get("same_doc_claims_only", True),
                            erlaeuterungsbericht_claims_only=q.get("erlaeuterungsbericht_claims_only", False),
                            exclude_local_claims=q.get("exclude_local_claims", False),
                            exclude_claim_ids=q.get("exclude_claim_ids"),
                        ),
                        limit=q["k_neighbors"],
                        with_payload=False,
                        with_vector=False,
                        score_threshold=score_lower_threshold,
                    )
                )

        # Send in batches, collect flat responses.
        flat_responses: list[Any] = []
        for i in range(0, len(flat_requests), batch_size):
            batch = flat_requests[i : i + batch_size]
            batch_result = self.query_batch_points(
                collection_name=collection_name,
                requests=batch,
            )
            flat_responses.extend(batch_result)

        # Re-shape flat responses back to [claim_index][query_index].
        result: list[list[list[str]]] = []
        for claim_idx in range(len(claim_payloads)):
            claim_results: list[list[str]] = []
            for q_idx in range(n_queries):
                resp = flat_responses[claim_idx * n_queries + q_idx]
                claim_results.append(
                    [
                        str(record.id)
                        for record in resp.points
                        if record.score is not None and score_lower_threshold <= record.score <= score_upper_threshold
                    ]
                )
            result.append(claim_results)

        return result

    def _parse_payload_records(
        self,
        records: list[Any],
        model_cls: type[TPayload],
        with_vectors: bool,
        payload_name: str,
    ) -> list[TPayload]:
        parsed_payloads: list[TPayload] = []

        for record in records:
            if not record.payload:
                activity.logger.warning("%s %s has no payload; skipping", payload_name, record.id)
                continue

            payload_data = dict(record.payload)
            if with_vectors:
                payload_data["vector"] = record.vector

            parsed_payloads.append(model_cls.model_validate(payload_data))

        return parsed_payloads

    def _get_single_payload(
        self,
        get_payloads_fn: Callable[..., list[TPayload]],
        project_id: str,
        record_id: str,
        label: str,
        with_vector: bool = False,
    ) -> TPayload:
        payloads = get_payloads_fn(project_id, [record_id], with_vectors=with_vector)

        if not payloads:
            raise ApplicationError(
                f"{label} {record_id} not found for project {project_id}.",
                non_retryable=True,
            )

        if len(payloads) > 1:
            raise ApplicationError(
                f"Found {len(payloads)} {label.lower()}s with ID {record_id} in project {project_id}",
                non_retryable=True,
            )

        return payloads[0]

    def get_parent_chunk_payloads(
        self, project_id: str, parent_chunk_ids: list[str], with_vectors: bool = False
    ) -> list[ParentChunkPayload]:
        if not parent_chunk_ids:
            return []

        records = self._get_record_payloads(
            project_id=project_id,
            point_ids=parent_chunk_ids,
            collection="parent_chunks",
            with_vectors=with_vectors,
        )

        return self._parse_payload_records(
            records=records,
            model_cls=ParentChunkPayload,
            with_vectors=with_vectors,
            payload_name="Parent chunk",
        )

    def get_parent_chunk_payload(
        self, project_id: str, parent_chunk_id: str, with_vector: bool = False
    ) -> ParentChunkPayload:
        return self._get_single_payload(
            self.get_parent_chunk_payloads, project_id, parent_chunk_id, "Parent chunk", with_vector
        )

    def get_chunk_payloads(
        self, project_id: str, chunk_ids: list[str], with_vectors: bool = False
    ) -> list[ChunkPayload]:
        """Retrieve chunk payloads for the provided chunk IDs."""
        if not chunk_ids:
            return []

        records = self._get_record_payloads(
            project_id=project_id,
            point_ids=chunk_ids,
            collection="chunks",
            with_vectors=with_vectors,
        )

        return self._parse_payload_records(
            records=records,
            model_cls=ChunkPayload,
            with_vectors=with_vectors,
            payload_name="Chunk",
        )

    def get_chunk_payload(self, project_id: str, chunk_id: str, with_vector: bool = False) -> ChunkPayload:
        return self._get_single_payload(self.get_chunk_payloads, project_id, chunk_id, "Chunk", with_vector)

    def _traverse_linked_chunks(
        self,
        project_id: str,
        start_id: str | None,
        count: int,
        direction: Literal["previous", "next"],
    ) -> list[ChunkPayload]:
        """Walk a linked-list of chunks in the given direction, returning up to ``count`` payloads."""
        chunks: list[ChunkPayload] = []
        current_id = start_id
        for _ in range(count):
            if not current_id:
                break
            chunk = self.get_chunk_payload(project_id=project_id, chunk_id=current_id)
            chunks.append(chunk)
            current_id = chunk.previous_chunk_id if direction == "previous" else chunk.next_chunk_id
        return chunks

    def get_chunk_payload_with_neighbors(
        self,
        project_id: str,
        chunk_id: str,
        prev: int = 1,
        n_next: int = 1,
    ) -> tuple[ChunkPayload, list[ChunkPayload], list[ChunkPayload]]:
        """Retrieve the chunk payload for the given chunk ID along with its previous and next neighbors."""
        base = self.get_chunk_payload(project_id=project_id, chunk_id=chunk_id)
        previous_chunks = self._traverse_linked_chunks(project_id, base.previous_chunk_id, prev, "previous")
        next_chunks = self._traverse_linked_chunks(project_id, base.next_chunk_id, n_next, "next")
        return base, previous_chunks, next_chunks

    def get_claim_payloads(
        self, project_id: str, claim_ids: list[str], with_vectors: bool = False
    ) -> list[ClaimPayload]:
        """Retrieve claim payloads for the provided claim IDs."""
        if not claim_ids:
            return []

        records = self._get_record_payloads(
            project_id=project_id,
            point_ids=claim_ids,
            collection="claims",
            with_vectors=with_vectors,
        )

        return self._parse_payload_records(
            records=records,
            model_cls=ClaimPayload,
            with_vectors=with_vectors,
            payload_name="Claim",
        )

    def get_claim_payload(self, project_id: str, claim_id: str, with_vector: bool = False) -> ClaimPayload:
        return self._get_single_payload(self.get_claim_payloads, project_id, claim_id, "Claim", with_vector)

    def get_chunk_ids_by_document_id(self, project_id: str, document_id: str) -> list[str]:
        """Retrieve all chunk IDs associated with a specific document ID."""
        collection_name = self._get_collection_name(project_id, "chunks")
        collection_must_conditions = self.get_collection_must_conditions(project_id, "chunks")
        collection_must_conditions.append(
            models.FieldCondition(
                key="source_file_id",
                match=models.MatchValue(value=document_id),
            )
        )
        collection_filter = models.Filter(must=collection_must_conditions)
        return self._get_record_ids(
            collection_name=collection_name,
            collection_filter=collection_filter,
        )

    async def delete_collections(self, project_id: str) -> None:
        """Remove an existing Qdrant collection if it exists.

        Args:
            project_id: Identifier used to locate the project's collection.

        Raises:
            RuntimeError: If the collection deletion fails.
        """
        claim_collection_name = self._get_collection_name(project_id, "claims")
        chunk_collection_name = self._get_collection_name(project_id, "chunks")
        try:
            self.delete_collection(collection_name=claim_collection_name)
        except Exception as exc:
            raise RuntimeError(f"Failed to delete collection {claim_collection_name}: {exc}") from exc
        try:
            self.delete_collection(collection_name=chunk_collection_name)
        except Exception as exc:
            raise RuntimeError(f"Failed to delete chunk collection {chunk_collection_name}: {exc}") from exc

    def get_claim_ids(self, document_id: str, project_id: str) -> list[str]:
        """Retrieve all claim IDs for a given document."""
        collection_name = self._get_collection_name(project_id, "claims")
        collection_must_conditions = self.get_collection_must_conditions(project_id, "claims")
        collection_must_conditions.append(
            models.FieldCondition(
                key="document_id",
                match=models.MatchValue(value=document_id),
            )
        )
        collection_filter = models.Filter(must=collection_must_conditions)

        all_claim_ids = self._get_record_ids(
            collection_name=collection_name,
            collection_filter=collection_filter,
        )

        return all_claim_ids
