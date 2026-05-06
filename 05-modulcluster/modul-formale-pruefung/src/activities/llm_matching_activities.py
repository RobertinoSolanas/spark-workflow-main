"""Temporal activities for the LLM-based document matching workflow.

This module contains the activity definitions used to load configuration data,
generate summaries specifically for classification, and perform the actual
matching of documents against a predefined list of types using an LLM.
"""

from prompt_injection.prompt_defense import render_prompt
from temporalio import activity

from src.config.config import config
from src.models.llm_client import LLMClient
from src.prompts.llm_matching_prompts import (
    DOCUMENT_GROUPING_SYSTEM_PROMPT,
    DOCUMENT_GROUPING_USER_PROMPT,
    DOCUMENT_MATCHING_SYSTEM_PROMPT,
    DOCUMENT_MATCHING_USER_PROMPT,
    DOCUMENT_SUMMARIZATION_SYSTEM_PROMPT,
    DOCUMENT_SUMMARIZATION_USER_PROMPT,
    UNASSIGNED_ANALYSIS_SYSTEM_PROMPT,
    UNASSIGNED_ANALYSIS_USER_PROMPT,
)
from src.schemas.llm_matching_schemas import (
    ClassificationSummaryActivityParams,
    DocumentClassificationMatchResult,
    DocumentGroup,
    DocumentGroupingActivityParams,
    DocumentGroupingResult,
    DocumentMatchingActivityParams,
    DocumentSummaryGenerationResult,
    UnassignedDocumentAnalysisParams,
    UnassignedDocumentReason,
)


@activity.defn
async def llm_classification_summary(
    params: ClassificationSummaryActivityParams,
) -> str:
    """Generates a classification-optimized summary for a document using an LLM.

    This activity constructs a prompt using the document's name, existing generic
    summary, and a text chunk, then queries the LLM to produce a summary
    specifically designed to aid in the document type matching process (focusing
    on format, technical content, and key identifiers).

    Args:
        params (ClassificationSummaryActivityParams): The parameters containing
            document details (name, summary, chunk) and the LLM profile to use.

    Returns:
        str: The generated summary string optimized for classification.
    """
    llm = LLMClient(
        system_prompt=DOCUMENT_SUMMARIZATION_SYSTEM_PROMPT,
        response_format=DocumentSummaryGenerationResult,
        profile=config.LLM_MATCHING.LLM_PROFILE,
    )
    user_prompt = render_prompt(
        DOCUMENT_SUMMARIZATION_USER_PROMPT,
        document_name=params.document_name,
        document_summary=params.document_summary,
        chunk=params.chunk,
    )
    res: DocumentSummaryGenerationResult = await llm.ainvoke(prompt=user_prompt)

    return res.summary_for_classification


@activity.defn
async def llm_document_grouping(
    params: DocumentGroupingActivityParams,
) -> list[DocumentGroup]:
    """Groups a list of documents logically based on filenames using an LLM.

    This activity takes a list of unsorted filenames and uses an LLM to identify
    logical groups. It returns a list of DocumentGroup objects referencing input
    indices.

    Validation Logic:
    It strictly validates that all returned indices (representative_index and
    document_indices) fall within the bounds of the input document list.
    Any group containing out-of-bound indices is discarded to prevent downstream errors.

    Args:
        params (DocumentGroupingActivityParams): The parameters containing the list
            of document names and the LLM profile to use.

    Returns:
        List[DocumentGroup]: A list of valid identified document groups.
    """
    llm = LLMClient(
        system_prompt=DOCUMENT_GROUPING_SYSTEM_PROMPT,
        response_format=DocumentGroupingResult,
        profile=config.LLM_MATCHING.LLM_PROFILE,
    )
    user_prompt = render_prompt(DOCUMENT_GROUPING_USER_PROMPT, document_names=params.document_names)
    res: DocumentGroupingResult = await llm.ainvoke(prompt=user_prompt)

    valid_groups = []
    num_docs = len(params.document_names)

    for group in res.groups:
        if not (0 <= group.representative_index < num_docs):
            activity.logger.warning(
                f"Grouping hallucination: Representative index {group.representative_index} "
                f"is out of bounds (0-{num_docs - 1}). Discarding group '{group.group_name}'."
            )
            continue

        invalid_indices = [idx for idx in group.document_indices if not (0 <= idx < num_docs)]

        if invalid_indices:
            activity.logger.warning(
                f"Grouping hallucination: Document indices {invalid_indices} "
                f"are out of bounds (0-{num_docs - 1}). Discarding group '{group.group_name}'."
            )
            continue

        valid_groups.append(group)

    return valid_groups


@activity.defn
async def llm_match_document_to_list(
    params: DocumentMatchingActivityParams,
) -> DocumentClassificationMatchResult:
    """Identifies the best matching document type from a candidate list using an LLM.

    This activity presents the LLM with the document's classification summary and
    a list of candidate document types. It analyzes the semantic fit and returns
    a structured result containing the best match index, reasoning, and confidence.

    Validation Logic:
    It validates that the returned `match_index` is within the valid range of the
    `candidate_list`. If the index is out of bounds, it is forcibly reset to -1
    (indicating no match).

    Args:
        params (DocumentMatchingActivityParams): The parameters containing the
            document info, the candidate list objects, and the LLM profile.

    Returns:
        DocumentClassificationMatchResult: The complete matching result object.
    """
    llm = LLMClient(
        system_prompt=DOCUMENT_MATCHING_SYSTEM_PROMPT,
        response_format=DocumentClassificationMatchResult,
        profile=config.LLM_MATCHING.LLM_PROFILE,
    )

    user_prompt = render_prompt(
        DOCUMENT_MATCHING_USER_PROMPT,
        document_name=params.document_name,
        document_summary=params.document_summary,
        document_group=params.document_group,
        candidates=params.candidate_list,
    )
    res: DocumentClassificationMatchResult = await llm.ainvoke(prompt=user_prompt)

    if res.match_index < 0 or res.match_index >= len(params.candidate_list):
        if res.match_index != -1:
            activity.logger.warning(
                f"Matching hallucination: Index {res.match_index} is out of bounds "
                f"(0-{len(params.candidate_list) - 1}). Resetting to -1."
            )
        res.match_index = -1

    return res


@activity.defn
async def llm_analyze_unassigned_document(
    params: UnassignedDocumentAnalysisParams,
) -> UnassignedDocumentReason:
    """Analyzes why a document remains unassigned after classification attempts.

    This activity encapsulates the prompt logic. It takes the raw document info
    and the list of rejection reasons, formats them into a prompt internally,
    and returns a synthesized summary of why the document is unassigned.

    Args:
        params (UnassignedDocumentAnalysisParams): Contains document details and the list
            of rejection strings from the matching attempts.

    Returns:
        str: A concise paragraph explaining the unassigned status.
    """
    llm = LLMClient(
        system_prompt=UNASSIGNED_ANALYSIS_SYSTEM_PROMPT,
        response_format=UnassignedDocumentReason,
        profile=config.LLM_MATCHING.LLM_PROFILE,
    )
    user_prompt = render_prompt(
        UNASSIGNED_ANALYSIS_USER_PROMPT,
        document_name=params.document_name,
        document_summary=params.document_summary,
        reasoning_history=params.reasoning_history,
    )
    return await llm.ainvoke(prompt=user_prompt)
