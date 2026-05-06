import math

import networkx as nx
from prompt_injection.prompt_defense import (
    sanitize_and_wrap_external_data,
    wrap_system_prompt,
)
from temporalio import activity

from src.config.config import config
from src.workflows.check_logic_wf.prompts.cluster_summarizer_prompts import (
    CLUSTER_SUMMARIZER_SYSTEM_PROMPT,
)
from src.workflows.check_logic_wf.schemas.cluster_summarizer_schemas import (
    ClusteringInput,
    InconsistencyCluster,
    InconsistencyClusters,
    InconsistencyGraph,
    InconsistencySummary,
    IndexedInconsistencyEdge,
    SummarizerResponse,
)
from src.workflows.check_logic_wf.schemas.output_schemas import Occurrence
from src.workflows.clients import llm_client, qdrant_client


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


@activity.defn
async def summarize_cluster(cluster: InconsistencyCluster) -> SummarizerResponse:
    """Summarize one inconsistency cluster from indexed graph evidence."""
    # Build LLM-safe graph representation (UUID-like chunk IDs -> local ints).
    indexed_edges: list[IndexedInconsistencyEdge] = []
    node_idx_to_trace: dict[int, dict[str, str | int | None]] = {}

    # Build a deterministic mapping from chunk IDs to node indices.
    chunk_id_to_node_index: dict[str, int] = {}
    next_node_index = 0

    for edge in cluster.edges:
        if edge.chunk_a_id not in chunk_id_to_node_index:
            chunk_id_to_node_index[edge.chunk_a_id] = next_node_index
            next_node_index += 1
        if edge.chunk_b_id not in chunk_id_to_node_index:
            chunk_id_to_node_index[edge.chunk_b_id] = next_node_index
            next_node_index += 1

    # Build indexed edges using the local node mapping.
    for edge in cluster.edges:
        node_a_idx = chunk_id_to_node_index[edge.chunk_a_id]
        node_b_idx = chunk_id_to_node_index[edge.chunk_b_id]
        if node_a_idx not in node_idx_to_trace:
            node_idx_to_trace[node_a_idx] = {
                "document_name": edge.chunk_a_document_name,
                "page_number": edge.chunk_a_page_number,
            }
        if node_b_idx not in node_idx_to_trace:
            node_idx_to_trace[node_b_idx] = {
                "document_name": edge.chunk_b_document_name,
                "page_number": edge.chunk_b_page_number,
            }
        indexed_edges.append(
            IndexedInconsistencyEdge(
                node_a_idx=node_a_idx,
                node_b_idx=node_b_idx,
                content_a_excerpt=edge.content_a_excerpt,
                content_b_excerpt=edge.content_b_excerpt,
                title=edge.title,
                explanation=edge.explanation,
            )
        )
    graph_representation = InconsistencyGraph(edges=indexed_edges)

    system_prompt = wrap_system_prompt(CLUSTER_SUMMARIZER_SYSTEM_PROMPT, lang="de")
    user_prompt = sanitize_and_wrap_external_data(graph_representation.model_dump_json(indent=2))

    llm_response = await llm_client.ainvoke(
        system_prompt=system_prompt,
        output_format=InconsistencySummary,
        user_prompt=user_prompt,
    )
    summary = InconsistencySummary.model_validate(llm_response)
    excerpt_by_node_idx = {e.node_idx: e.excerpt for e in summary.content_excerpts}
    occurrences = []
    for stance in summary.stances:
        trace = node_idx_to_trace.get(stance.node_idx, {})
        occurrences.append(
            Occurrence(  # pyrefly: ignore[missing-argument]  # populate_by_name=True allows snake_case
                document_id=cluster.document_id,
                document_name=str(trace["document_name"])
                if "document_name" in trace and trace["document_name"] is not None
                else None,
                page_number=trace.get("page_number"),
                content_excerpt=excerpt_by_node_idx.get(stance.node_idx, stance.stance_text),
                contradiction=stance.stance_text,
            )
        )
    return SummarizerResponse(inconsistencies=[summary.model_copy(update={"occurrences": occurrences})])


@activity.defn
async def build_clusters(clustering_input: ClusteringInput) -> InconsistencyClusters:
    """Cluster contradiction pairs by shared claim or semantic similarity of claims."""
    pairs = clustering_input.inconsistency_pairs
    project_id = clustering_input.project_id

    # Collect all unique claim IDs and fetch their vectors in one batch call.
    all_claim_ids = list({cid for pair in pairs for cid in (pair.claim_a_id, pair.claim_b_id)})
    claim_payloads = qdrant_client.get_claim_payloads(
        project_id=project_id,
        claim_ids=all_claim_ids,
        with_vectors=True,
    )
    vectors: dict[str, list[float]] = {
        p.claim_metadata.claim_id: p.vector for p in claim_payloads if p.vector is not None
    }

    # Build a graph over pair indices: add edge when two pairs should be merged.
    graph = nx.Graph()
    threshold = config.SUMMARIZING.SIMILARITY_THRESHOLD
    for i, pair_a in enumerate(pairs):
        for j, pair_b in enumerate(pairs):
            if j <= i:
                continue
            claims_a = {pair_a.claim_a_id, pair_a.claim_b_id}
            claims_b = {pair_b.claim_a_id, pair_b.claim_b_id}

            should_merge = bool(claims_a & claims_b)  # shared claim

            if not should_merge:
                for cid_a in claims_a:
                    for cid_b in claims_b:
                        if cid_a in vectors and cid_b in vectors:
                            if _cosine_similarity(vectors[cid_a], vectors[cid_b]) >= threshold:
                                should_merge = True
                                break
                    if should_merge:
                        break

            if should_merge:
                graph.add_edge(i, j)

    # Isolated pairs must appear as single-node components.
    for i in range(len(pairs)):
        if i not in graph:
            graph.add_node(i)

    clusters = []
    for component in nx.connected_components(graph):  # type: ignore[attr-defined]
        cluster_pairs = [pairs[i] for i in sorted(component)]
        if config.SUMMARIZING.MAX_EDGES_PER_CLUSTER is not None:
            # Safety measure to prevent huge LLM inputs downstream.
            cluster_pairs = cluster_pairs[: config.SUMMARIZING.MAX_EDGES_PER_CLUSTER]
        clusters.append(
            InconsistencyCluster(
                edges=cluster_pairs,
                document_id=clustering_input.document_id,
            )
        )

    return InconsistencyClusters(clusters=clusters)
