# src/activities/pageindex_structure/tree_builder.py
"""
Pure tree manipulation logic for PageIndex structure extraction.

No LLM calls, no Temporal imports — only deterministic tree/node operations.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import tiktoken

logger = logging.getLogger("uvicorn")

# Use cl100k_base directly — it's a reasonable approximation for any model
# and avoids coupling to a specific OpenAI model name.
_ENCODING = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str | None) -> int:
    if not text:
        return 0
    return len(_ENCODING.encode(text))


def write_node_id(data: dict[str, Any] | list[Any], node_id: int = 0) -> int:
    if isinstance(data, dict):
        data["node_id"] = str(node_id).zfill(4)
        node_id += 1
        for key in list(data.keys()):
            if "nodes" in key:
                node_id = write_node_id(data[key], node_id)
    elif isinstance(data, list):
        for index in range(len(data)):
            node_id = write_node_id(data[index], node_id)
    return node_id


def structure_to_list(structure: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    if isinstance(structure, dict):
        nodes: list[dict[str, Any]] = []
        nodes.append(structure)
        if "nodes" in structure and structure["nodes"] is not None:
            nodes.extend(structure_to_list(structure["nodes"]))
        return nodes
    elif isinstance(structure, list):
        nodes_list: list[dict[str, Any]] = []
        for item in structure:
            nodes_list.extend(structure_to_list(item))
        return nodes_list
    return []


def reorder_dict(data: dict[str, Any], key_order: list[str]) -> dict[str, Any]:
    if not key_order:
        return data
    return {key: data[key] for key in key_order if key in data}


def format_structure(
    structure: dict[str, Any] | list[Any], order: list[str] | None = None
) -> dict[str, Any] | list[Any]:
    if not order:
        return structure
    if isinstance(structure, dict):
        if "nodes" in structure:
            structure["nodes"] = format_structure(structure["nodes"], order)
        if not structure.get("nodes"):
            structure.pop("nodes", None)
        structure = reorder_dict(structure, order)
    elif isinstance(structure, list):
        structure = [format_structure(item, order) for item in structure]
    return structure


def _flatten_structure_nodes(
    structure: dict[str, Any] | list[Any],
) -> list[dict[str, Any]]:
    """Recursively flatten a hierarchical structure into a list of all nodes (depth-first)."""
    nodes: list[dict[str, Any]] = []
    if isinstance(structure, dict):
        nodes.append(structure)
        if "nodes" in structure:
            nodes.extend(_flatten_structure_nodes(structure["nodes"]))
    elif isinstance(structure, list):
        for item in structure:
            nodes.extend(_flatten_structure_nodes(item))
    return nodes


def add_page_information(toc_tree: dict[str, Any], md_content: str) -> dict[str, Any]:
    """Add page number information to all nodes in the structure tree.

    Handles both flat (root-only) and nested (hierarchical) structures
    by flattening all nodes, computing character boundaries from line_num,
    then matching against page markers in the markdown.
    """
    page_pattern = r'<seite\s+nummer="(\d+)"\s*/?>'
    line_entries = list(re.finditer("\n", md_content))
    map_line_to_character: dict[int, int] = {i_line: e.span()[0] for i_line, e in enumerate(line_entries)}
    page_starts: list[tuple[int, int]] = [(e.span()[0], int(e.group(1))) for e in re.finditer(page_pattern, md_content)]

    if not page_starts:
        logger.warning("No page markers found in markdown content")
        return toc_tree

    page_info: list[tuple[int, int, int]] = []
    for idx in range(len(page_starts) - 1):
        page_start, page_number = page_starts[idx]
        page_end = page_starts[idx + 1][0]
        page_info.append((page_start, page_end, page_number))
    page_info.append((page_starts[-1][0], len(md_content), page_starts[-1][1]))

    all_nodes = _flatten_structure_nodes(toc_tree["structure"])
    if not all_nodes:
        return toc_tree

    all_nodes_sorted = sorted(all_nodes, key=lambda n: n["line_num"])

    node_char_boundaries: dict[str, tuple[int, int]] = {}
    for i, node in enumerate(all_nodes_sorted):
        current_line = node["line_num"] - 1
        if current_line not in map_line_to_character:
            logger.warning(
                f"Line {node['line_num']} not found in line-to-character map, skipping node '{node.get('title', '')}'"
            )
            continue
        char_start = map_line_to_character[current_line]
        if i + 1 < len(all_nodes_sorted):
            next_line = all_nodes_sorted[i + 1]["line_num"] - 1
            if next_line in map_line_to_character:
                char_end = map_line_to_character[next_line]
            else:
                char_end = page_starts[-1][0] + 1
        else:
            char_end = page_starts[-1][0] + 1
        node_char_boundaries[node["node_id"]] = (char_start, char_end)

    for node in all_nodes:
        node_id = node["node_id"]
        if node_id not in node_char_boundaries:
            empty_pages: list[int] = []
            node["pages"] = empty_pages
            continue
        char_start, char_end = node_char_boundaries[node_id]
        lst_pages: list[int] = []
        for page_start, page_end, page_number in page_info:
            if page_start <= char_end and page_end >= char_start:
                lst_pages.append(page_number)
        node["pages"] = lst_pages

    return toc_tree


def extract_nodes_from_markdown(
    markdown_content: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Extract markdown header nodes and return them with their line numbers."""
    header_pattern = r"^(#{1,6})\s+(.+)$"
    node_list: list[dict[str, Any]] = []

    lines = markdown_content.split("\n")

    for line_num, line in enumerate(lines, 1):
        stripped_line = line.strip()

        if not stripped_line:
            continue

        match = re.match(header_pattern, stripped_line)
        if match:
            title = match.group(2).strip()
            node_list.append({"node_title": title, "line_num": line_num})

    return node_list, lines


def extract_node_text_content(node_list: list[dict[str, Any]], markdown_lines: list[str]) -> list[dict[str, Any]]:
    """Attach the full text content between each header and the next to each node."""
    all_nodes: list[dict[str, Any]] = []
    for node in node_list:
        line_content = markdown_lines[node["line_num"] - 1]
        header_match = re.match(r"^(#{1,6})", line_content)

        if header_match is None:
            logger.warning(f"Line {node['line_num']} does not contain a valid header: '{line_content}'")
            continue

        processed_node: dict[str, Any] = {
            "title": node["node_title"],
            "line_num": node["line_num"],
            "level": len(header_match.group(1)),
        }
        all_nodes.append(processed_node)

    for i, node in enumerate(all_nodes):
        start_line = node["line_num"] - 1
        if i + 1 < len(all_nodes):
            end_line = all_nodes[i + 1]["line_num"] - 1
        else:
            end_line = len(markdown_lines)

        node["text"] = "\n".join(markdown_lines[start_line:end_line]).strip()
    return all_nodes


def update_node_list_with_text_token_count(
    node_list: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compute cumulative token counts for each node including all descendant text."""

    def find_all_children(parent_index: int, parent_level: int, node_list: list[dict[str, Any]]) -> list[int]:
        """Find all direct and indirect children of a parent node."""
        children_indices: list[int] = []
        for i in range(parent_index + 1, len(node_list)):
            current_level = node_list[i]["level"]
            if current_level <= parent_level:
                break
            children_indices.append(i)
        return children_indices

    result_list = node_list.copy()

    for i in range(len(result_list) - 1, -1, -1):
        current_node = result_list[i]
        current_level = current_node["level"]

        children_indices = find_all_children(i, current_level, result_list)

        node_text = current_node.get("text", "")
        total_text = node_text

        for child_index in children_indices:
            child_text = result_list[child_index].get("text", "")
            if child_text:
                total_text += "\n" + child_text

        result_list[i]["text_token_count"] = count_tokens(total_text)

    return result_list


def tree_thinning_for_index(node_list: list[dict[str, Any]], min_node_token: int | None = None) -> list[dict[str, Any]]:
    """Merge nodes below the minimum token threshold into their parent."""

    def find_all_children(parent_index: int, parent_level: int, node_list: list[dict[str, Any]]) -> list[int]:
        """Find all descendant indices of the node at parent_index."""
        children_indices: list[int] = []
        for i in range(parent_index + 1, len(node_list)):
            current_level = node_list[i]["level"]
            if current_level <= parent_level:
                break
            children_indices.append(i)
        return children_indices

    result_list = node_list.copy()
    nodes_to_remove: set[int] = set()

    for i in range(len(result_list) - 1, -1, -1):
        if i in nodes_to_remove:
            continue

        current_node = result_list[i]
        current_level = current_node["level"]

        total_tokens = current_node.get("text_token_count", 0)

        if total_tokens < min_node_token:
            children_indices = find_all_children(i, current_level, result_list)

            children_texts: list[str] = []
            for child_index in sorted(children_indices):
                if child_index not in nodes_to_remove:
                    child_text = result_list[child_index].get("text", "")
                    if child_text.strip():
                        children_texts.append(child_text)
                    nodes_to_remove.add(child_index)

            if children_texts:
                parent_text = current_node.get("text", "")
                merged_text = parent_text
                for child_text in children_texts:
                    if merged_text and not merged_text.endswith("\n"):
                        merged_text += "\n\n"
                    merged_text += child_text

                result_list[i]["text"] = merged_text

                result_list[i]["text_token_count"] = count_tokens(merged_text)

    for index in sorted(nodes_to_remove, reverse=True):
        result_list.pop(index)

    return result_list


def build_tree_from_nodes(
    node_list: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build a nested tree structure from a flat list of nodes based on heading levels."""
    if not node_list:
        return []

    stack: list[tuple[dict[str, Any], int]] = []
    root_nodes: list[dict[str, Any]] = []
    node_counter = 1

    for node in node_list:
        current_level = node["level"]

        tree_node: dict[str, Any] = {
            "title": node["title"],
            "node_id": str(node_counter).zfill(4),
            "text": node["text"],
            "line_num": node["line_num"],
            "nodes": [],
        }
        node_counter += 1

        while stack and stack[-1][1] >= current_level:
            stack.pop()

        if not stack:
            root_nodes.append(tree_node)
        else:
            parent_node, parent_level = stack[-1]
            parent_node["nodes"].append(tree_node)

        stack.append((tree_node, current_level))

    return root_nodes


def clean_tree_for_output(
    tree_nodes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Remove internal-only keys from tree nodes, keeping only output-relevant fields."""
    cleaned_nodes: list[dict[str, Any]] = []

    for node in tree_nodes:
        cleaned_node: dict[str, Any] = {
            "title": node["title"],
            "node_id": node["node_id"],
            "text": node["text"],
            "line_num": node["line_num"],
        }

        if node["nodes"]:
            cleaned_node["nodes"] = clean_tree_for_output(node["nodes"])

        cleaned_nodes.append(cleaned_node)

    return cleaned_nodes
