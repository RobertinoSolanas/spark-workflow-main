# ruff: noqa: E402
from temporal.observability import (
    ObservabilityConfig,
    setup_observability,
    shutdown_observability,
)

from src.env import ENV

setup_observability(
    ObservabilityConfig(
        service_name=ENV.OTEL_SERVICE_NAME,
        otel_endpoint=ENV.OTEL_ENDPOINT,
    )
)

import asyncio

from temporal.s3_payload_storage import S3PayloadStorage
from temporal.worker import start_temporal_worker

from src.activities.chunk_enrichment import _merge_all_enrichment_results
from src.activities.dms_activities import (
    _delete_file_activity,
    _download_file_activity,
    _get_file_metadata_activity,
    _list_files_activity,
    _resolve_priority_file,
    _upload_file_activity,
)
from src.activities.extraction import _extract_document_direct
from src.activities.hypothetical_questions import (
    _process_hypo_questions_batch,
)
from src.activities.llm_invoke import _llm_invoke_structured
from src.activities.pageindex_structure import (
    _create_pageindex_json,
    _get_structure_list_valid_files,
)
from src.activities.postprocessing import (
    _chunk_markdown,
    _create_final_json,
    _create_summary_from_results,
    _filter_enhance_content,
    _prepare_vlm_inputs_activity,
    _split_markdown_by_pages,
    _upload_images_to_dms,
)
from src.activities.preprocessing import _convert_to_pdf_if_needed
from src.activities.qdrant import (
    _get_inhalts_extraktion_docs,
    _index_document_to_qdrant,
    _init_qdrant_collection,
)
from src.activities.schwerpunkt_extraction import (
    _process_schwerpunkt_batch,
)
from src.activities.species_scale_extraction import (
    _process_species_scale_batch,
)
from src.activities.summarization import (
    _combine_summaries,
    _summarize_chunks_batch,
)
from src.activities.vlm_invoke import (
    _vlm_invoke,
)
from src.activities.vlm_processing import _apply_vlm_results, _summarize_visual_element
from src.env import ENV
from src.services.docling_processing import (
    _combine_docling_chunks,
    _compress_pdf_images,
    _deduplicate_images,
    _download_and_prepare_pdf,
    _extract_chunk_with_docling,
    _rasterize_chunk,
    _split_pdf_for_docling,
    _upload_debug_files_docling,
)
from src.workflows.chunk_enrichment.workflow import ChunkEnrichmentWorkflow
from src.workflows.extraction.docling_workflow import DoclingExtractionWorkflow
from src.workflows.helpers.base_metadata_extractor import _consolidate_base_metadata
from src.workflows.hypothetical_questions.workflow import HypotheticalQuestionsWorkflow
from src.workflows.pageindex_structure.workflow import (
    PageindexStructureWorkflow,
    SingleFileStructureWorkflow,
)
from src.workflows.process_documents_workflow import ProcessDocumentsWorkflow
from src.workflows.qdrant.workflow import QdrantBuilderWorkflow
from src.workflows.schwerpunkt.workflow import SchwerpunktWorkflow
from src.workflows.single_document_workflow import SingleDocumentWorkflow
from src.workflows.species_scale.workflow import SpeciesScaleWorkflow
from src.workflows.summarization.document_workflow import DocumentSummarizationWorkflow
from src.workflows.summarization.workflow import SummarizationWorkflow
from src.workflows.vlm_enhancement.batch_workflow import VLMProcessingWorkflow
from src.workflows.vlm_enhancement.workflow import VLMWorkflow


async def main() -> None:
    storage = S3PayloadStorage(
        bucket_name=ENV.TEMPORAL_S3_BUCKET_NAME,
        endpoint_url=ENV.TEMPORAL_S3_ENDPOINT_URL,
        access_key=ENV.TEMPORAL_S3_ACCESS_KEY_ID.get_secret_value(),
        secret_key=ENV.TEMPORAL_S3_SECRET_ACCESS_KEY.get_secret_value(),
        region=ENV.TEMPORAL_S3_REGION,
    )
    try:
        await asyncio.gather(
            start_temporal_worker(
                host=ENV.TEMPORAL_SERVER_URL,
                task_queue=ENV.TEMPORAL_TASK_QUEUE,
                storage=storage,
                workflows=[
                    ProcessDocumentsWorkflow,
                    SingleDocumentWorkflow,
                    DoclingExtractionWorkflow,
                    VLMProcessingWorkflow,
                    VLMWorkflow,
                    DocumentSummarizationWorkflow,
                    SummarizationWorkflow,
                    SchwerpunktWorkflow,
                    HypotheticalQuestionsWorkflow,
                    SpeciesScaleWorkflow,
                    ChunkEnrichmentWorkflow,
                    QdrantBuilderWorkflow,
                    SingleFileStructureWorkflow,
                    PageindexStructureWorkflow,
                ],
                activities=[
                    _convert_to_pdf_if_needed,
                    _extract_document_direct,
                    _compress_pdf_images,
                    _download_and_prepare_pdf,
                    _rasterize_chunk,
                    _split_pdf_for_docling,
                    _extract_chunk_with_docling,
                    _combine_docling_chunks,
                    _deduplicate_images,
                    _upload_debug_files_docling,
                    _consolidate_base_metadata,
                    _filter_enhance_content,
                    _upload_images_to_dms,
                    _chunk_markdown,
                    _split_markdown_by_pages,
                    _prepare_vlm_inputs_activity,
                    _apply_vlm_results,
                    _create_final_json,
                    _create_summary_from_results,
                    _summarize_chunks_batch,
                    _process_schwerpunkt_batch,
                    _process_hypo_questions_batch,
                    _process_species_scale_batch,
                    _merge_all_enrichment_results,
                    _llm_invoke_structured,
                    _vlm_invoke,
                    _download_file_activity,
                    _get_file_metadata_activity,
                    _upload_file_activity,
                    _list_files_activity,
                    _delete_file_activity,
                    _resolve_priority_file,
                    _summarize_visual_element,
                    _combine_summaries,
                    _get_inhalts_extraktion_docs,
                    _init_qdrant_collection,
                    _index_document_to_qdrant,
                    # Pageindex structure activities
                    _create_pageindex_json,
                    _get_structure_list_valid_files,
                ],
            ),
        )
    finally:
        shutdown_observability()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
