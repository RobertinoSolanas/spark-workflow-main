from src.activities.dms_activities import (
    download_json_from_dms,
    get_inhalts_extraktion_doc_chunks,
    get_inhalts_extraktion_docs,
    upload_temporal_checkpoint,
)
from src.activities.inhaltsverzeichnis_finder_activities import (
    llm_chunk_classification,
    llm_connected_chunk_classification,
    llm_document_type_description_generation,
    llm_inhaltsverzeichnis_parser,
    llm_overall_classification,
    llm_select_global_inhaltsverzeichnis_document_name,
)
from src.activities.llm_matching_activities import (
    llm_analyze_unassigned_document,
    llm_classification_summary,
    llm_document_grouping,
    llm_match_document_to_list,
)

llm_activities = [
    llm_classification_summary,
    llm_match_document_to_list,
    llm_chunk_classification,
    llm_connected_chunk_classification,
    llm_document_type_description_generation,
    llm_inhaltsverzeichnis_parser,
    llm_overall_classification,
    llm_select_global_inhaltsverzeichnis_document_name,
    llm_document_grouping,
    llm_analyze_unassigned_document,
]

non_llm_activities = [
    get_inhalts_extraktion_docs,
    get_inhalts_extraktion_doc_chunks,
    upload_temporal_checkpoint,
    download_json_from_dms,
]

activities = llm_activities + non_llm_activities
