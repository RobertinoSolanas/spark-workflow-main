# src/activities/pageindex_structure/__init__.py
"""
PageIndex structure extraction — re-exports all public names for backward compatibility.
"""

from .activities import (
    CreatePageindexJsonInput,
    CreatePageindexJsonOutput,
    _create_pageindex_json,
    _get_structure_list_valid_files,
    create_pageindex_json,
    create_pageindex_structure,
    get_structure_list_valid_files,
    md_to_tree,
)
from .summarization import (
    MAX_TOKENS_PER_CHUNK,
    generate_long_summary,
    generate_node_summary,
    generate_summaries_for_structure_md,
    get_node_summary,
    recursive_summary,
)
from .tree_builder import (
    add_page_information,
    build_tree_from_nodes,
    clean_tree_for_output,
    count_tokens,
    extract_node_text_content,
    extract_nodes_from_markdown,
    format_structure,
    reorder_dict,
    structure_to_list,
    tree_thinning_for_index,
    update_node_list_with_text_token_count,
    write_node_id,
)

__all__ = [
    # tree_builder
    "count_tokens",
    "write_node_id",
    "structure_to_list",
    "reorder_dict",
    "format_structure",
    "add_page_information",
    "extract_nodes_from_markdown",
    "extract_node_text_content",
    "update_node_list_with_text_token_count",
    "tree_thinning_for_index",
    "build_tree_from_nodes",
    "clean_tree_for_output",
    # summarization
    "MAX_TOKENS_PER_CHUNK",
    "recursive_summary",
    "generate_long_summary",
    "generate_node_summary",
    "get_node_summary",
    "generate_summaries_for_structure_md",
    # activities
    "CreatePageindexJsonInput",
    "CreatePageindexJsonOutput",
    "md_to_tree",
    "create_pageindex_structure",
    "_get_structure_list_valid_files",
    "_create_pageindex_json",
    "get_structure_list_valid_files",
    "create_pageindex_json",
]
