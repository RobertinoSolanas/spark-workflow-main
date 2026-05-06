import asyncio

from prompt_injection.prompt_defense import sanitize_and_wrap_external_data, wrap_system_prompt
from temporalio import activity

from src.config.config import config
from src.qdrant.schemas import ClaimPayload
from src.workflows.check_logic_wf.prompts.risk_screener_prompts import (
    RISK_SCREENER_SYSTEM_PROMPT,
)
from src.workflows.check_logic_wf.schemas.risk_screener_schemas import (
    DocumentBundleRequest,
    DocumentBundleResult,
    RiskScreenerIndexedResponse,
    RiskScreenerItem,
    RiskScreenerPromptPayload,
    RiskScreenerReferencePromptItem,
    RiskScreenerResponse,
    ScreeningBundleResult,
    ScreeningCandidateBundle,
    ScreeningHit,
)
from src.workflows.clients import llm_client, qdrant_client


def _index_reference_claims(
    reference_claims: dict[str, ClaimPayload],
) -> tuple[dict[int, ClaimPayload], dict[int, str]]:
    """Map claim UUIDs to 1-based indices for prompting and back-translation."""
    reference_by_idx: dict[int, ClaimPayload] = {}
    idx_to_uuid: dict[int, str] = {}
    for reference_index, (ref_uuid, ref_payload) in enumerate(reference_claims.items(), start=1):
        reference_by_idx[reference_index] = ref_payload
        idx_to_uuid[reference_index] = ref_uuid
    return reference_by_idx, idx_to_uuid


def _translate_screening_results(
    screening_result_dict: dict[int, RiskScreenerItem],
    idx_to_uuid: dict[int, str],
) -> dict[str, RiskScreenerItem]:
    """Translate LLM result keys (indices) back to UUIDs."""
    translated: dict[str, RiskScreenerItem] = {}
    for reference_index, item in screening_result_dict.items():
        ref_uuid = idx_to_uuid.get(reference_index)
        if not ref_uuid:
            continue
        translated[ref_uuid] = item
    return translated


async def _screen_inconsistency_risks(
    check_claim_payload: ClaimPayload,
    reference_claim_payloads: list[ClaimPayload],
) -> RiskScreenerResponse:
    """Ask the screening LLM to assess which referenced claims are high-risk."""
    reference_by_idx, idx_to_uuid = _index_reference_claims(
        {payload.claim_id: payload for payload in reference_claim_payloads}
    )
    prompt_payload = RiskScreenerPromptPayload(
        check_claim_text=check_claim_payload.claim_text,
        reference_claims=[
            RiskScreenerReferencePromptItem(
                reference_id=ref_idx,
                claim_text=ref_claim_payload.claim_text,
            )
            for ref_idx, ref_claim_payload in reference_by_idx.items()
        ],
    )

    system_prompt = wrap_system_prompt(RISK_SCREENER_SYSTEM_PROMPT, lang="de")
    user_prompt = sanitize_and_wrap_external_data(prompt_payload.model_dump_json(indent=2))

    llm_response = await llm_client.ainvoke(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        output_format=RiskScreenerIndexedResponse,
    )
    screening_response = RiskScreenerIndexedResponse.model_validate(llm_response)
    translated = _translate_screening_results(screening_response.screening_result_dict, idx_to_uuid)
    return RiskScreenerResponse(screening_result_dict=translated)


@activity.defn
async def build_screening_bundles_for_document(
    request: DocumentBundleRequest,
) -> DocumentBundleResult:
    """Build screening bundles for all claims in a document using batched Qdrant queries.

    Fetches all claim vectors and chunk payloads in bulk, then issues all KNN queries
    in configurable-size batches. Returns raw bundles (one per claim) without
    deduplication — symmetric-pair deduplication is the caller's responsibility.
    """
    k_overfetch = (
        config.RISK_SCREENING.K_ERLAEUTERUNGSBERICHT_COMPARISON_CLAIMS + config.RISK_SCREENING.K_LOCAL_COMPARISON_CLAIMS
    )

    # Bulk-fetch all claim payloads with vectors.
    claim_payloads = await asyncio.to_thread(
        qdrant_client.get_claim_payloads,
        project_id=request.project_id,
        claim_ids=request.claim_ids,
        with_vectors=True,
    )
    # Preserve the caller's ordering.
    claim_payload_by_id = {p.claim_id: p for p in claim_payloads}
    ordered_claim_payloads = [claim_payload_by_id[cid] for cid in request.claim_ids if cid in claim_payload_by_id]

    # Bulk-fetch all chunk payloads needed for local-exclusion filters.
    unique_chunk_ids = list({p.chunk_id for p in ordered_claim_payloads if p.chunk_id})
    chunk_payloads_list = await asyncio.to_thread(
        qdrant_client.get_chunk_payloads,
        project_id=request.project_id,
        chunk_ids=unique_chunk_ids,
    )
    chunk_payloads_by_id = {cp.chunk_id: cp for cp in chunk_payloads_list}

    # The 3-query spec is identical for every claim; only the vector and filters differ.
    queries_per_claim = [
        {
            "k_neighbors": config.RISK_SCREENING.K_ERLAEUTERUNGSBERICHT_COMPARISON_CLAIMS,
            "exclude_local_claims": True,
            "same_doc_claims_only": False,
            "erlaeuterungsbericht_claims_only": True,
        },
        {
            "k_neighbors": config.RISK_SCREENING.K_LOCAL_COMPARISON_CLAIMS,
            "same_doc_claims_only": True,
            "exclude_local_claims": False,
        },
        {
            "k_neighbors": config.RISK_SCREENING.K_TOTAL_COMPARISON_CLAIMS + k_overfetch,
            "same_doc_claims_only": True,
            "exclude_local_claims": True,
        },
    ]

    # Issue all (claim × query) combinations in batches.
    all_results = await asyncio.to_thread(
        qdrant_client.get_claim_knn_ids_all_claims_batched,
        project_id=request.project_id,
        claim_payloads=ordered_claim_payloads,
        chunk_payloads_by_id=chunk_payloads_by_id,
        queries_per_claim=queries_per_claim,
        batch_size=config.RISK_SCREENING.QDRANT_QUERY_BATCH_SIZE,
    )

    bundles: list[ScreeningCandidateBundle] = []
    for claim_payload, (erlaeuterungsbericht_refs, same_doc_refs_local_allowed, same_doc_refs_no_local_raw) in zip(
        ordered_claim_payloads, all_results, strict=False
    ):
        q1_q2_ids = set(erlaeuterungsbericht_refs + same_doc_refs_local_allowed)
        same_doc_refs_no_local = [ref_id for ref_id in same_doc_refs_no_local_raw if ref_id not in q1_q2_ids]

        k_erlaeuterungsbericht_found = len(erlaeuterungsbericht_refs)
        k_local_found = len(same_doc_refs_local_allowed)
        k_remaining = max(
            0,
            config.RISK_SCREENING.K_TOTAL_COMPARISON_CLAIMS - k_erlaeuterungsbericht_found - k_local_found,
        )

        candidate_reference_claim_ids = (erlaeuterungsbericht_refs + same_doc_refs_local_allowed)[
            : config.RISK_SCREENING.K_TOTAL_COMPARISON_CLAIMS
        ]
        candidate_reference_claim_ids += same_doc_refs_no_local[:k_remaining]
        candidate_reference_claim_ids = candidate_reference_claim_ids[: config.RISK_SCREENING.K_TOTAL_COMPARISON_CLAIMS]

        bundles.append(
            ScreeningCandidateBundle(
                project_id=request.project_id,
                document_id=request.document_id,
                claim_id=claim_payload.claim_id,
                reference_claims=candidate_reference_claim_ids,
            )
        )

    return DocumentBundleResult(bundles=bundles)


@activity.defn
async def screen_claim_bundle(
    screening_candidate_bundle: ScreeningCandidateBundle,
) -> ScreeningBundleResult:
    """Screen one claim against its candidate references via the screener LLM.

    Args:
        screening_candidate_bundle: Candidate references for one check claim.

    Returns:
        ScreeningBundleResult with claim pairs at or above the configured risk threshold.
    """
    hits: list[ScreeningHit] = []

    primary_claim_payload = qdrant_client.get_claim_payload(
        project_id=screening_candidate_bundle.project_id,
        claim_id=screening_candidate_bundle.claim_id,
        with_vector=False,
    )

    reference_claim_payloads = qdrant_client.get_claim_payloads(
        project_id=screening_candidate_bundle.project_id,
        claim_ids=screening_candidate_bundle.reference_claims,
        with_vectors=False,
    )

    screening_response = await _screen_inconsistency_risks(
        check_claim_payload=primary_claim_payload,
        reference_claim_payloads=reference_claim_payloads,
    )

    for reference_claim_id, screening_item in screening_response.screening_result_dict.items():
        if screening_item.rating < config.RISK_SCREENING.RATING_THRESHOLD:
            continue

        hits.append(
            ScreeningHit(
                claim_id=primary_claim_payload.claim_id,
                reference_id=reference_claim_id,
                rating=screening_item.rating,
                note=screening_item.note,
                reasoning=screening_item.reasoning,
            )
        )

    return ScreeningBundleResult(hits=hits)
