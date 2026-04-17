"""Defines Temporal Activities for the Table of Contents (TOC) extraction workflow.

This module contains the activity definitions required by the
`InhaltsverzeichnisFinderWorkflow`. These activities handle the orchestration
of external services, including:
1.  **Data Fetching:** Retrieving document metadata and text chunks from the
    Inhaltsextraktion API.
2.  **LLM Classification:** Using an OpenAI-compatible LLM to classify text chunks
    as potential TOCs, verify them against document context, and determine if
    subsequent chunks are logical continuations.

The activities bridge the gap between the Temporal workflow engine and the
domain-specific logic for document analysis.
"""

from prompt_injection.prompt_defense import render_prompt
from temporalio import activity, workflow

with workflow.unsafe.imports_passed_through():
    from src.config.config import config
    from src.models.llm_client import LLMClient
    from src.prompts.inhaltsverzeichnis_finder_prompts import (
        DOCUMENT_TYPE_DESCRIPTION_GENERATION_SYSTEM_PROMPT,
        DOCUMENT_TYPE_DESCRIPTION_GENERATION_USER_PROMPT,
        FILENAME_SELECTION_SYSTEM_PROMPT,
        FILENAME_SELECTION_USER_PROMPT,
        INHALTSVERZEICHNIS_CHUNK_CLASSIFICATION_SYSTEM_PROMPT,
        INHALTSVERZEICHNIS_CHUNK_CLASSIFICATION_USER_PROMPT,
        INHALTSVERZEICHNIS_CONNECTED_CHUNK_CLASSIFICATION_SYSTEM_PROMPT,
        INHALTSVERZEICHNIS_CONNECTED_CHUNK_CLASSIFICATION_USER_PROMPT,
        INHALTSVERZEICHNIS_OVERALL_CLASSIFICATION_SYSTEM_PROMPT,
        INHALTSVERZEICHNIS_OVERALL_CLASSIFICATION_USER_PROMPT,
        INHALTSVERZEICHNIS_PARSER_SYSTEM_PROMPT,
        INHALTSVERZEICHNIS_PARSER_USER_PROMPT,
    )
    from src.schemas.inhaltsverzeichnis_finder_schemas import (
        ChunkLLMClassificationActivityParams,
        ConnectedChunkLLMClassificationActivityParams,
        DocumentTypeDescriptionGenerationActivityInput,
        DocumentTypeDescriptionResult,
        FileNameClassificationResult,
        InhaltsverzeichnisClassificationResult,
        InhaltsverzeichnisConnectedChunksClassificationResult,
        InhaltsverzeichnisParsedResult,
        InhaltsverzeichnisParserActivityInput,
        OverallLLMClassificationActivityParams,
        SelectInhaltsverzeichnisLLMActivityParams,
    )


@activity.defn
async def llm_chunk_classification(
    params: ChunkLLMClassificationActivityParams,
) -> InhaltsverzeichnisClassificationResult:
    """Classifies a text chunk to determine if it represents a Table of Contents.

    Args:
        chunk: The text content of the document chunk to classify.

    Returns:
        True if the chunk is identified as a global Table of Contents, False otherwise.
    """
    activity.logger.debug(f"Starting basic LLM classification for chunk (len={len(params.chunk)})")

    llm = LLMClient(
        system_prompt=INHALTSVERZEICHNIS_CHUNK_CLASSIFICATION_SYSTEM_PROMPT,
        response_format=InhaltsverzeichnisClassificationResult,
        profile=config.INHALTSVERZEICHNIS_FINDER.LLM_PROFILE,
    )
    user_prompt = render_prompt(INHALTSVERZEICHNIS_CHUNK_CLASSIFICATION_USER_PROMPT, chunk=params.chunk)
    res: InhaltsverzeichnisClassificationResult = await llm.ainvoke(prompt=user_prompt)

    activity.logger.debug(f"Basic classification result: {res.is_global_inhalts_verzeichnis}")
    return res


@activity.defn
async def llm_overall_classification(
    params: OverallLLMClassificationActivityParams,
) -> InhaltsverzeichnisClassificationResult:
    """Classifies a chunk using document context (name and summary).

    Performs a more context-aware classification to determine if the chunk
    serves as the global Table of Contents for the specific document.

    Args:
        params: Parameters containing the chunk text, document name, summary and llm profile.

    Returns:
        True if the chunk is identified as a global Table of Contents, False otherwise.
    """
    activity.logger.debug(f"Starting overall (context-aware) classification for document: '{params.document_name}'")

    llm = LLMClient(
        system_prompt=INHALTSVERZEICHNIS_OVERALL_CLASSIFICATION_SYSTEM_PROMPT,
        response_format=InhaltsverzeichnisClassificationResult,
        profile=config.INHALTSVERZEICHNIS_FINDER.LLM_PROFILE,
    )
    user_prompt = render_prompt(
        INHALTSVERZEICHNIS_OVERALL_CLASSIFICATION_USER_PROMPT,
        document_name=params.document_name,
        document_summary=params.document_summary,
        chunk=params.chunk,
    )
    res: InhaltsverzeichnisClassificationResult = await llm.ainvoke(prompt=user_prompt)

    activity.logger.debug(
        f"Overall classification result for '{params.document_name}': {res.is_global_inhalts_verzeichnis}"
    )
    return res


@activity.defn
async def llm_select_global_inhaltsverzeichnis_document_name(
    params: SelectInhaltsverzeichnisLLMActivityParams,
) -> int | None:
    """
    Analyzes a list of filenames to identify the most likely global Master Index.

    Args:
        params: Parameters containing the list of filenames to evaluate and llm profile.

    Returns:
        The 0-based index of the chosen file, or None if no suitable candidate is found.
    """
    activity.logger.debug(f"Starting file name selection. Candidates: {len(params.document_names)}")

    formatted_file_list = "\n".join([f"[{i}] {name}" for i, name in enumerate(params.document_names)])

    llm = LLMClient(
        system_prompt=FILENAME_SELECTION_SYSTEM_PROMPT,
        response_format=FileNameClassificationResult,
        profile=config.INHALTSVERZEICHNIS_FINDER.LLM_PROFILE,
    )

    user_prompt = render_prompt(FILENAME_SELECTION_USER_PROMPT, file_names_list=formatted_file_list)

    res: FileNameClassificationResult = await llm.ainvoke(prompt=user_prompt)

    chosen_index = res.chosen_file_index
    activity.logger.debug(f"LLM selected index: '{chosen_index}'")

    if chosen_index == -1:
        return None

    if chosen_index < 0 or chosen_index >= len(params.document_names):
        activity.logger.warning(
            f"LLM returned an invalid index ({chosen_index}) for a list ofsize {len(params.document_names)}"
        )
        return None

    activity.logger.debug(f"Selected index {chosen_index} corresponds to '{params.document_names[chosen_index]}'")

    return chosen_index


@activity.defn
async def llm_connected_chunk_classification(
    params: ConnectedChunkLLMClassificationActivityParams,
) -> bool:
    """Determines if two text chunks are sequentially connected.

    Evaluates whether the second chunk is a logical continuation of the first,
    typically used to identify Table of Contents spanning multiple pages.

    Args:
        params: Parameters containing the first, second text chunks and llm profile.

    Returns:
        True if the chunks are determined to be connected, False otherwise.
    """
    activity.logger.debug(
        f"Checking connection between chunks. "
        f"Chunk 1 len: {len(params.first_chunk)}, Chunk 2 len: {len(params.second_chunk)}"
    )

    llm = LLMClient(
        system_prompt=INHALTSVERZEICHNIS_CONNECTED_CHUNK_CLASSIFICATION_SYSTEM_PROMPT,
        response_format=InhaltsverzeichnisConnectedChunksClassificationResult,
        profile=config.INHALTSVERZEICHNIS_FINDER.LLM_PROFILE,
    )
    user_prompt = render_prompt(
        INHALTSVERZEICHNIS_CONNECTED_CHUNK_CLASSIFICATION_USER_PROMPT,
        first_chunk=params.first_chunk,
        second_chunk=params.second_chunk,
    )
    res: InhaltsverzeichnisConnectedChunksClassificationResult = await llm.ainvoke(prompt=user_prompt)

    activity.logger.debug(f"Chunks connected status: {res.are_connected_chunks}")
    return res.are_connected_chunks


@activity.defn
async def llm_inhaltsverzeichnis_parser(
    params: InhaltsverzeichnisParserActivityInput,
) -> InhaltsverzeichnisParsedResult:
    """Parses extracted table-of-contents chunks into a structured TOC object using an LLM.

    This activity consolidates a list of text chunks representing a document's
    Table of Contents (TOC) into a single text block. It then invokes a Large
    Language Model (LLM) to analyze the text and extract the lowest-level
    elements (leaf nodes) into a structured format, preserving their hierarchical
    context as defined in the `InhaltsverzeichnisParsedResult` schema.

    Args:
        params (InhaltsverzeichnisParserActivityInput): The input parameters for the activity.
            This is expected to contain:
            - chunk_list: A sequence of document chunks (objects with a `page_content` attribute)
              representing the raw text of the TOC.
            - llm_profile: Configuration settings for the LLM client (e.g., model name,
              temperature, API keys).

    Returns:
        InhaltsverzeichnisParsedResult: The structured result containing a list of
        extracted TOC entries (`InhaltsverzeichnisLeafEntry`), each with its title,
        hierarchy path, and optional numbering.
    """
    full_text = "\n\n".join(chunk.page_content for chunk in params.chunk_list)

    injected_user_prompt = render_prompt(INHALTSVERZEICHNIS_PARSER_USER_PROMPT, iv_str=full_text)
    llm = LLMClient(
        system_prompt=INHALTSVERZEICHNIS_PARSER_SYSTEM_PROMPT,
        response_format=InhaltsverzeichnisParsedResult,
        profile=config.INHALTSVERZEICHNIS_FINDER.LLM_PROFILE,
    )
    response: InhaltsverzeichnisParsedResult = await llm.ainvoke(injected_user_prompt)

    return response


@activity.defn
async def llm_document_type_description_generation(
    params: DocumentTypeDescriptionGenerationActivityInput,
) -> DocumentTypeDescriptionResult:
    """
    Call the LLM to generate a short contextual explanation for a chapter
    or subchapter based on the given GIV fields and project metadata.

    If `subchapter_id` is set, the subchapter template is used, otherwise
    the chapter template is used.
    """
    llm = LLMClient(
        system_prompt=DOCUMENT_TYPE_DESCRIPTION_GENERATION_SYSTEM_PROMPT,
        response_format=DocumentTypeDescriptionResult,
        profile=config.INHALTSVERZEICHNIS_FINDER.LLM_PROFILE,
    )

    user_prompt = render_prompt(
        DOCUMENT_TYPE_DESCRIPTION_GENERATION_USER_PROMPT,
        entry_title=params.entry_title,
        entry_number=params.entry_number,
        hierarchy_path=" > ".join(params.hierarchy_path) if params.hierarchy_path else "None",
        document_definitions=params.document_types,
    )
    response: DocumentTypeDescriptionResult = await llm.ainvoke(user_prompt)
    return response
