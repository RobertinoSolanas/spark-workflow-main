from pydantic import BaseModel, Field

from src.workflows.check_logic_wf.schemas.output_schemas import Occurrence


class InconsistencyPair(BaseModel):
    """Edge evidence connecting two chunks that appear inconsistent."""

    chunk_a_id: str = Field(description="Chunk ID for one side of the contradiction.")
    chunk_b_id: str = Field(description="Chunk ID for the opposite side.")
    claim_a_id: str = Field(description="Claim ID for one side of the contradiction.")
    claim_b_id: str = Field(description="Claim ID for the opposite side.")

    content_a_excerpt: str = Field(description="Supporting excerpt from chunk A.")
    content_b_excerpt: str = Field(description="Supporting excerpt from chunk B.")
    chunk_a_document_name: str | None = Field(
        default=None,
        description="Human-readable source document title for chunk A.",
    )
    chunk_b_document_name: str | None = Field(
        default=None,
        description="Human-readable source document title for chunk B.",
    )
    chunk_a_page_number: int | None = Field(
        default=None,
        description="Representative page number for chunk A.",
    )
    chunk_b_page_number: int | None = Field(
        default=None,
        description="Representative page number for chunk B.",
    )

    title: str = Field(description="Short contradiction label.")
    explanation: str = Field(description="Context-checker explanation for this edge.")


class ClusteringInput(BaseModel):
    """Input for graph-based clustering of verified inconsistencies."""

    project_id: str = Field(description="Project scope for this clustering run.")
    document_id: str = Field(description="Document whose inconsistencies are clustered.")
    inconsistency_pairs: list[InconsistencyPair] = Field(
        description="Verified pairwise inconsistencies used as graph edges."
    )


class IndexedInconsistencyEdge(BaseModel):
    """Prompt-safe edge format using local integer node IDs instead of UUIDs."""

    node_a_idx: int = Field(description="Local node index for chunk A.")
    node_b_idx: int = Field(description="Local node index for chunk B.")

    content_a_excerpt: str = Field(description="Supporting excerpt for node A.")
    content_b_excerpt: str = Field(description="Supporting excerpt for node B.")

    title: str = Field(description="Short contradiction label for this edge.")
    explanation: str = Field(description="Explanation for this edge.")


class InconsistencyGraph(BaseModel):
    """Graph payload rendered into the summarizer prompt."""

    edges: list[IndexedInconsistencyEdge] = Field(description="Indexed contradiction edges in the cluster.")


class InconsistencyCluster(BaseModel):
    """One connected component of inconsistency edges plus summarizer config."""

    edges: list[InconsistencyPair] = Field(description="Contradiction edges belonging to this cluster.")
    document_id: str = Field(description="Document ID shared by all edges in this cluster.")


class InconsistencyClusters(BaseModel):
    """Collection of connected inconsistency clusters for one document."""

    clusters: list[InconsistencyCluster] = Field(description="Connected components to summarize.")


class NodeStance(BaseModel):
    """A single node's position within a contradiction cluster."""

    node_idx: int = Field(description="Local node index this stance belongs to.")
    stance_text: str = Field(
        max_length=400,
        description="Short neutral description of what this content states.",
    )


class NodeExcerpt(BaseModel):
    """A verbatim excerpt for one node in a contradiction cluster."""

    node_idx: int = Field(description="Local node index this excerpt belongs to.")
    excerpt: str = Field(
        max_length=500,
        description="Verbatim excerpt from the source text for this node.",
    )


class InconsistencySummary(BaseModel):
    """LLM summary for one inconsistency cluster."""

    cluster_title: str = Field(
        max_length=150,
        description="Short headline for the contradiction cluster.",
    )
    cluster_explanation: str = Field(
        max_length=800,
        description="Consolidated explanation of the contradiction across stances.",
    )
    stances: list[NodeStance] = Field(
        description="List of node stances representing distinct positions found in the cluster."
    )
    content_excerpts: list[NodeExcerpt] = Field(description="List of node excerpts preserved for traceability.")
    occurrences: list[Occurrence] = Field(
        default_factory=list,
        description="Resolved occurrences enriched with document and page metadata.",
    )


class SummarizerResponse(BaseModel):
    """Response payload returned by the cluster summarizer LLM."""

    inconsistencies: list[InconsistencySummary] = Field(
        description="Summaries generated for the provided cluster graph."
    )
