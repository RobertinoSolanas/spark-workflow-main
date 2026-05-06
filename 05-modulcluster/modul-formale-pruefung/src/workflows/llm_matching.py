import asyncio
from datetime import timedelta

from pydantic import ValidationError
from temporal.workflows.formale_pruefung.llm_matching import LLM_MATCHING_WORKFLOW_ID
from temporal.workflows.formale_pruefung.types import (
    DMSFileResponse,
    DocumentOutput,
    LLMMatchingOutput,
    LLMMatchingParams,
    MatchedDocumentTypeOutput,
)
from temporalio import workflow
from temporalio.common import RetryPolicy

from src.activities.dms_activities import (
    UploadTemporalCheckpointInput,
    get_inhalts_extraktion_doc_chunks,
    get_inhalts_extraktion_docs,
    upload_temporal_checkpoint,
)
from src.activities.llm_matching_activities import (
    llm_analyze_unassigned_document,
    llm_classification_summary,
    llm_document_grouping,
    llm_match_document_to_list,
)
from src.config.config import config
from src.schemas.dms_schemas import (
    InhaltsExtraktionChunksActivityParams,
)
from src.schemas.llm_matching_schemas import (
    ClassificationSummaryActivityParams,
    DocumentClassificationMatchResult,
    DocumentData,
    DocumentGroup,
    DocumentGroupingActivityParams,
    DocumentMatchingActivityParams,
    DocumentTypeDefinition,
    UnassignedDocumentAnalysisParams,
)
from src.utils.external_preprocessing import external_document_type_preprocessing
from src.utils.sliding_window import sliding_window


@workflow.defn(name=LLM_MATCHING_WORKFLOW_ID)
class LLMMatchingWorkflow:
    """
    Workflow that matches documents from a project against a predefined list of document
    types using a two-stage LLM process (Summarization -> Matching).
    """

    @workflow.run
    async def run(self, params: LLMMatchingParams) -> DMSFileResponse:
        """
        Orchestrates the document matching process.

        Args:
            params (LLMMatchingParams): Configuration parameters for the workflow,
                including timeouts, paths, and project IDs.

        Returns:
            DMSFileResponse: The result of temporal workflows is uploaded to DMS for
                simple storage, access and to avoid size limitation. It is a json using the
                LLMMatchingOutput format which contains the matched and
                unmatched documents.
        """
        workflow.logger.info(f"Starting LLM Matching Workflow for project {params.project_id}")

        # 1. Load Definitions
        document_types = await self._load_document_types(params)
        if not document_types:
            workflow.logger.warning("No document definitions loaded.")
            empty_output = LLMMatchingOutput(matched_document_types=[], unassigned_documents=[])
            return await self._upload_result(empty_output, params)

        # 2. Fetch Files
        workflow.logger.debug("Fetching project files ...")
        documents = await self._fetch_documents(params=params)

        # 3. Perform Matching
        llm_matching_workflow_output = await self._match_documents(
            docs=documents,
            candidates=document_types,
            params=params,
        )
        # 4. Upload result
        upload = await self._upload_result(llm_matching_workflow_output, params)
        workflow.logger.info("LLM Matching Workflow completed successfully.")
        return upload

    async def _fetch_documents(self, params: LLMMatchingParams) -> list[DocumentData]:
        """
        Fetches documents via activity execution and wraps them into DocumentData objects
        while marking which documents should be classified if params.document_ids is set.

        Args:
            params (LLMMatchingParams): The workflow params containing project_id,
                document_ids.
        Returns:
            List[DocumentData]: A list of prepared document data structures.
        """
        dms_files = await workflow.execute_activity(
            get_inhalts_extraktion_docs,
            params.project_id,
            start_to_close_timeout=timedelta(seconds=config.TEMPORAL.ACTIVITY_TIMEOUT_SECONDS),
            retry_policy=RetryPolicy(maximum_attempts=config.TEMPORAL.ACTIVITY_MAX_RETRIES),
        )
        workflow.logger.info(f"Fetched {len(dms_files)} documents for processing.")
        documents = []
        for d in dms_files:
            should_classify = True
            if params.document_ids and d.document_id not in params.document_ids:
                should_classify = False
            documents.append(
                DocumentData(
                    dms_doc=d,
                    should_classify=should_classify,
                )
            )
        return documents

    async def _load_document_types(
        self,
        params: LLMMatchingParams,
    ) -> list[DocumentTypeDefinition]:
        """Loads and optionally preprocesses document type definitions.

        If `params.external_preprocessing` is True, it assumes the raw data is in external
        format. Finally, it validates the data against the `DocumentTypeDefinition`
        Pydantic model.

        Args:
            params: Configuration object containing:
                - document_types: Optional raw JSON string.
                - external_preprocessing: Boolean flag to trigger structural conversion.

        Returns:
            List[DocumentTypeDefinition]: A list of validated document type definitions.
            Returns an empty list if data loading or parsing fails.
        """
        if not isinstance(params.document_types, list):
            workflow.logger.error(
                f"Validation failed: Expected data to be a List of definitions, got {type(params.document_types)}."
            )
            return []
        if params.external_preprocessing:
            workflow.logger.info("external Preprocessing enabled")
            try:
                params.document_types = external_document_type_preprocessing(params.document_types)
            except Exception:
                workflow.logger.exception("external preprocessing failed")
                raise
        validated_definitions = []
        for item in params.document_types:
            try:
                validated_model = DocumentTypeDefinition.model_validate(item)
                validated_definitions.append(validated_model)
            except ValidationError as e:
                workflow.logger.warning(f"Skipping invalid document definition item: {item}. Error: {e}")
                continue

        workflow.logger.info(f"Successfully loaded {len(validated_definitions)} document definitions.")
        return validated_definitions

    async def _retrieve_and_summarize_extracted_content(
        self, doc: DocumentData, params: LLMMatchingParams
    ) -> DocumentData:
        """
        Retrieves existing content extraction result and generates classification
        summary for the provided document.

        Args:
            documents (DocumentData): The source document.
            params (LLMMatchingParams): Parameters containing LLM configuration and timeouts.

        Returns:
            DocumentData: Documents enriched with inhalts_extraction and classification summary.
        """
        doc.inhalts_extraction = await workflow.execute_activity(
            get_inhalts_extraktion_doc_chunks,
            InhaltsExtraktionChunksActivityParams(
                dms_document=doc.dms_doc,
                n_pages=config.LLM_MATCHING.N_PAGE_SUMMARY,
                include_summary=True,
            ),
            start_to_close_timeout=timedelta(seconds=config.LLM_MATCHING.LLM_ACTIVITY_TIMEOUT_SECONDS),
            retry_policy=RetryPolicy(maximum_attempts=config.TEMPORAL.ACTIVITY_MAX_RETRIES),
        )
        doc.classification_summary = await workflow.execute_activity(
            llm_classification_summary,
            ClassificationSummaryActivityParams(
                document_name=doc.dms_doc.document_name,
                document_summary=doc.inhalts_extraction.summary or "",
                chunk="\n".join([chunk.page_content for chunk in doc.inhalts_extraction.chunks]),
            ),
            task_queue=f"{workflow.info().task_queue}-llm",
            start_to_close_timeout=timedelta(seconds=config.LLM_MATCHING.LLM_ACTIVITY_TIMEOUT_SECONDS),
            retry_policy=config.TEMPORAL.LLM_RETRY_POLICY,
        )
        return doc

    async def _batch_match_document(
        self,
        doc: DocumentData,
        batches: list[list[DocumentTypeDefinition]],
        params: LLMMatchingParams,
    ) -> tuple[list[tuple[DocumentTypeDefinition, DocumentClassificationMatchResult]], list[str]]:
        """Runs parallel LLM matching across candidate batches and collects results."""
        tasks = [
            workflow.execute_activity(
                llm_match_document_to_list,
                DocumentMatchingActivityParams(
                    document_name=doc.dms_doc.document_name,
                    document_summary=doc.classification_summary,
                    document_group=doc.document_group,
                    candidate_list=batch,
                ),
                task_queue=f"{workflow.info().task_queue}-llm",
                start_to_close_timeout=timedelta(seconds=config.LLM_MATCHING.LLM_ACTIVITY_TIMEOUT_SECONDS),
                retry_policy=config.TEMPORAL.LLM_RETRY_POLICY,
            )
            for batch in batches
        ]
        batch_results: list[DocumentClassificationMatchResult] = await asyncio.gather(*tasks)
        collected_reasoning = [f"Batch check: {e.reasoning}" for e in batch_results]
        potential_matches = [
            (batches[i][res.match_index], res) for i, res in enumerate(batch_results) if res.match_index != -1
        ]
        return potential_matches, collected_reasoning

    async def _match_document(
        self,
        doc: DocumentData,
        candidates: list[DocumentTypeDefinition],
        params: LLMMatchingParams,
    ) -> DocumentData:
        """Matches a single document against candidate definitions, handling context limits via a multi-stage process.

        This method employs a "map-reduce" style approach to handle cases where the
        number of candidate definitions exceeds the LLM's context window:
        1.  **Batching**: The full list of candidates is sliced into smaller batches
            based on `config.LLM_MATCHING.MAX_ELEMENTS_IN_CONTEXT`.
        2.  **First Pass**: Matching is attempted in parallel for each batch.
        3.  **Refinement**: If multiple batches return a match (indicating potential
            ambiguity or hallucination), a second "refinement" stage is executed
            against only the shortlisted candidates to determine the final winner.

        Args:
            doc (DocumentData): The metadata and summary of the document to be matched.
            candidates (List[DocumentTypeDefinition]): The complete registry of
                document definitions to match against.
            params (LLMMatchingParams): Configuration for batch sizes, timeouts, and
                concurrency limits.

        Returns:
            DocumentMatchingOutcome: The matching result containing
            the assigned type, reasoning, and confidence score. Returns None if no
            match is found in either the first stage or the refinement stage.
        """
        step = config.LLM_MATCHING.MAX_ELEMENTS_IN_CONTEXT
        batches = [candidates[i : i + step] for i in range(0, len(candidates), step)]
        doc = await self._retrieve_and_summarize_extracted_content(doc=doc, params=params)
        potential_matches, collected_reasoning = await self._batch_match_document(doc, batches, params)

        if potential_matches:
            if len(potential_matches) == 1:
                candidate, result = potential_matches[0]
                doc.assigned_document_type = candidate
                doc.reasoning = result.reasoning
                doc.confidence = result.confidence
                return doc

            workflow.logger.info(
                f"Document '{doc.dms_doc.document_name}' has "
                f"{len(potential_matches)} potential matches. Running refinement."
            )

            shortlist = [pm[0] for pm in potential_matches]
            refinement_res = await workflow.execute_activity(
                llm_match_document_to_list,
                DocumentMatchingActivityParams(
                    document_name=doc.dms_doc.document_name,
                    document_summary=doc.classification_summary,
                    document_group=doc.document_group,
                    candidate_list=shortlist,
                ),
                task_queue=f"{workflow.info().task_queue}-llm",
                start_to_close_timeout=timedelta(seconds=config.LLM_MATCHING.LLM_ACTIVITY_TIMEOUT_SECONDS),
                retry_policy=config.TEMPORAL.LLM_RETRY_POLICY,
            )
            collected_reasoning.append(f"Refinement check: {refinement_res.reasoning}")
            if refinement_res.match_index != -1:
                doc.assigned_document_type = shortlist[refinement_res.match_index]
                doc.reasoning = refinement_res.reasoning
                doc.confidence = refinement_res.confidence
                return doc
        unassigned_response = await workflow.execute_activity(
            llm_analyze_unassigned_document,
            UnassignedDocumentAnalysisParams(
                document_name=doc.dms_doc.document_name,
                document_summary=doc.classification_summary,
                reasoning_history=collected_reasoning,
            ),
            task_queue=f"{workflow.info().task_queue}-llm",
            start_to_close_timeout=timedelta(seconds=config.LLM_MATCHING.LLM_ACTIVITY_TIMEOUT_SECONDS),
            retry_policy=config.TEMPORAL.LLM_RETRY_POLICY,
        )
        doc.assigned_document_type = None
        doc.reasoning = unassigned_response.reasoning
        doc.confidence = unassigned_response.confidence
        return doc

    async def _process_matching_batch(
        self,
        indices: list[int],
        docs: list[DocumentData],
        candidates: list[DocumentTypeDefinition],
        params: LLMMatchingParams,
    ) -> dict[int, DocumentData]:
        """Helper to process a specific subset of documents concurrently with throttling.

        This method acts as a concurrency controller. It takes a list of indices
        (referring to `docs_data`) and processes them in chunks defined by
        `max_concurrent_files_for_match`. This prevents overloading the underlying
        LLM service or the workflow worker when processing large groups or remainder lists.

        Args:
            indices (List[int]): The specific indices in `docs_data` that need to be
                processed in this batch.
            docs_data (List[DocumentMatchingData]): The master list of all document data.
            candidates (List[DocumentTypeDefinition]): The list of candidates to match against.
            params (LLMMatchingParams): Execution parameters controlling concurrency
                chunk sizes.

        Returns:
            Dict[int, DocumentMatchingOutcome]: A mapping where
            keys are the document indices and values are the matching results (or None).
        """
        results_map = {}
        docs_batch_size = config.LLM_MATCHING.MAX_CONCURRENT_FILES_FOR_MATCH

        async def match_index(idx: int) -> tuple[int, DocumentData]:
            """Matches the document at index `idx` and returns it with its original index."""
            return idx, await self._match_document(docs[idx], candidates, params)

        results = await sliding_window(
            indices,
            match_index,
            concurrency=docs_batch_size,
        )
        for idx, res in results:
            results_map[idx] = res

        return results_map

    async def _match_documents(
        self,
        docs: list[DocumentData],
        candidates: list[DocumentTypeDefinition],
        params: LLMMatchingParams,
    ) -> LLMMatchingOutput:
        """Orchestrates the bulk matching of documents using a grouping optimization strategy.

        This workflow minimizes redundant processing and improves accuracy through a
        "Representative First" strategy:
        1.  **Grouping**: Documents are grouped based on their filenames and parent
            folder context (including Ordner names) to identify clusters of likely
            related files.
        2.  **Representative Matching**: A single representative document from each
            group is identified and matched first.
        3.  **Context Propagation**: The classification result of the representative
            is appended to the group name for the remaining members. For example, if
            the representative is an "Invoice", the group context becomes
            "Invoice - GroupName". This provides a strong hint to the LLM for the
            remaining documents.
        4.  **Remainder Matching**: The remaining non-representative documents are
            processed using this enhanced context.
        5.  **Aggregation**: Results are consolidated. If multiple documents match
            the same type, their confidences are aggregated.

        Args:
            docs_matching_data (List[DocumentMatchingData]): List of all documents
                requiring classification.
            candidates (List[DocumentTypeDefinition]): The definitions of possible
                document types.
            params (LLMMatchingParams): Parameters for timeouts, concurrency, and
                LLM profiles.

        Returns:
            LLMMatchingOutput: The final output separating successfully
            matched document types (with aggregated assigned documents) from
            unassigned documents.
        """
        workflow.logger.info(f"Matching {len(docs)} documents against {len(candidates)} definitions.")
        groups: list[DocumentGroup] = await workflow.execute_activity(
            llm_document_grouping,
            DocumentGroupingActivityParams(
                document_names=[d.dms_doc.document_name for d in docs],
            ),
            task_queue=f"{workflow.info().task_queue}-llm",
            start_to_close_timeout=timedelta(seconds=config.LLM_MATCHING.LLM_ACTIVITY_TIMEOUT_SECONDS),
            retry_policy=config.TEMPORAL.LLM_RETRY_POLICY,
        )
        results = []
        # Normally all groups are eligible; Only different when run on a subset of docs
        eligible_groups = [group for group in groups if any(docs[i].should_classify for i in group.document_indices)]
        repr_indices = [group.representative_index for group in eligible_groups]

        # 1. Process Representatives
        for group in groups:
            docs[group.representative_index].document_group = group.group_name

        repr_results = await self._process_matching_batch(repr_indices, docs, candidates, params)
        for group in eligible_groups:
            result = repr_results[group.representative_index]
            results.append(result)
            group_suffix = (
                f"{result.assigned_document_type.document_type_name} - {group.group_name}"
                if result.assigned_document_type
                else group.group_name
            )
            for member_idx in group.document_indices:
                docs[member_idx].document_group = group_suffix

        # 2. Process Remainder
        non_repr_indices = [i for i in range(len(docs)) if docs[i].should_classify and i not in repr_results]
        remainder_results = await self._process_matching_batch(non_repr_indices, docs, candidates, params)

        for _, result in remainder_results.items():
            results.append(result)
        return await self._build_output(results, candidates)

    async def _build_output(
        self,
        results: list[DocumentData],
        candidates: list[DocumentTypeDefinition],
    ) -> LLMMatchingOutput:
        """Constructs the structured output for the document matching workflow.

        Args:
            results: A list of outcomes generated from the document matching.
            candidates: A list of document type definitions that were used
                as the reference set for the matching task.

        Returns:
            An instance of LLMMatchingOutput containing the
            finalized matching data.
        """
        matched_types: dict[str, MatchedDocumentTypeOutput] = {}
        unassigned_docs: list[DocumentOutput] = []

        for document_type in candidates:
            matched_types[document_type.document_type_name] = MatchedDocumentTypeOutput(
                required_document_type=document_type,
                assigned_documents=[],
                confidence=0.0,
            )

        for doc in results:
            if not doc.should_classify:
                continue
            if not doc.assigned_document_type:
                unassigned_docs.append(
                    DocumentOutput(
                        document_name=doc.dms_doc.document_name,
                        document_id=doc.dms_doc.document_id,
                        document_extraction_id=doc.dms_doc.content_extraction_id,
                        reasoning=doc.reasoning,
                        confidence=doc.confidence,
                    )
                )
                continue
            type_name = doc.assigned_document_type.document_type_name
            output = DocumentOutput(
                document_name=doc.dms_doc.document_name,
                document_id=doc.dms_doc.document_id,
                document_extraction_id=doc.dms_doc.content_extraction_id,
                reasoning=doc.reasoning,
                confidence=doc.confidence,
            )
            entry = matched_types[type_name]
            if len(entry.assigned_documents) == 0:
                entry.confidence = round(doc.confidence, 2)
            else:
                entry.confidence = round(entry.confidence * doc.confidence, 2)
            entry.assigned_documents.append(output)
        return LLMMatchingOutput(
            matched_document_types=list(matched_types.values()),
            unassigned_documents=unassigned_docs,
        )

    async def _upload_result(
        self,
        output_data: LLMMatchingOutput,
        params: LLMMatchingParams,
    ) -> DMSFileResponse:
        """
        Executes the activity to upload the workflow results to the DMS.

        Args:
            output_data (LLMMatchingOutput): The structured workflow output
                to be serialized and uploaded.
            params (LLMMatchingParams): Workflow parameters containing configuration
                for retries and project identification.

        Returns:
            DMSFileResponse: The response from the DMS upload activity.
        """
        info = workflow.info()
        return await workflow.execute_activity(
            upload_temporal_checkpoint,
            UploadTemporalCheckpointInput(
                project_id=params.project_id,
                workflow_id=info.workflow_id,
                run_id=info.run_id,
                filename="result.json",
                payload=output_data.model_dump(mode="json"),
            ),
            start_to_close_timeout=timedelta(seconds=config.TEMPORAL.UPLOAD_ACTIVITY_TIMEOUT_SECONDS),
            retry_policy=RetryPolicy(maximum_attempts=config.TEMPORAL.ACTIVITY_MAX_RETRIES),
        )
