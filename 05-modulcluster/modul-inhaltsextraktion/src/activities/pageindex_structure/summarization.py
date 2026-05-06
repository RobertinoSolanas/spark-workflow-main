# src/activities/pageindex_structure/summarization.py
"""
LLM-based summary generation for PageIndex structure nodes.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.processors.text_splitters import RecursiveCharacterTextSplitter

from src.activities.llm_invoke import LlmInvokeInput, llm_invoke_structured_direct
from src.concurrency import get_model_throttle
from src.env import ENV
from src.models.model_manager import SelfHostedConfig
from src.workflows.pageindex_structure.prompt import (
    GENERATE_NODE_SUMMARY_SYSTEM_PROMPT,
    GENERATE_NODE_SUMMARY_USER_TEMPLATE,
    JOIN_SUMMARIES_SYSTEM_PROMPT,
    JOIN_SUMMARIES_USER_TEMPLATE,
)
from src.workflows.pageindex_structure.types import (
    NodeSummaryResponse,
    RecursiveSummaryResponse,
)

from .tree_builder import count_tokens, structure_to_list

logger = logging.getLogger("uvicorn")

MAX_TOKENS_PER_CHUNK = ENV.STRUCTURE_NODE_MAX_NODE_CHARS // 4

_STRUCTURE_LLM_CONFIG: SelfHostedConfig = {
    "provider": "self_hosted",
    "model_name": "structure",
}


async def recursive_summary(text: str, llm_config: SelfHostedConfig) -> str:
    """Recursively split and summarize text until it fits the character limit."""
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=ENV.STRUCTURE_NODE_MAX_NODE_CHARS // 4,
        chunk_overlap=200,
        keep_separator=True,
        is_separator_regex=False,
    )
    lst_summaries: list[str] = []
    for chunk_text in text_splitter.split_text(text):
        llm_result = await llm_invoke_structured_direct(
            input=LlmInvokeInput(
                llm_config=llm_config,
                prompt_template=GENERATE_NODE_SUMMARY_USER_TEMPLATE,
                input_dict={"node_text": chunk_text + " (...)"},
                agent_name="page_index_node_chunk_summary",
                system_prompt=GENERATE_NODE_SUMMARY_SYSTEM_PROMPT,
            ),
            output_class=NodeSummaryResponse,
        )
        lst_summaries.append(llm_result.summary)

    joint_summaries = "\n\n".join(lst_summaries)
    if len(joint_summaries) > ENV.STRUCTURE_NODE_MAX_NODE_CHARS:
        joint_summaries = await recursive_summary(joint_summaries, llm_config)

    return joint_summaries


async def generate_long_summary(text: str, llm_config: SelfHostedConfig) -> str:
    """Create long summaries by summarizing parts and then joining them through another LLM call."""
    joint_summaries = await recursive_summary(text, llm_config)

    llm_result = await llm_invoke_structured_direct(
        input=LlmInvokeInput(
            llm_config=llm_config,
            prompt_template=JOIN_SUMMARIES_USER_TEMPLATE,
            input_dict={"joint_summary": joint_summaries},
            agent_name="page_index_joint_summary",
            system_prompt=JOIN_SUMMARIES_SYSTEM_PROMPT,
        ),
        output_class=RecursiveSummaryResponse,
    )
    return llm_result.summary


async def generate_node_summary(node: dict[str, Any], llm_config: SelfHostedConfig) -> str:
    node_txt: str = node["text"]
    if len(node_txt) > ENV.STRUCTURE_NODE_MAX_NODE_CHARS:
        node_summary = await generate_long_summary(node_txt, llm_config)
    else:
        llm_result = await llm_invoke_structured_direct(
            input=LlmInvokeInput(
                llm_config=llm_config,
                prompt_template=GENERATE_NODE_SUMMARY_USER_TEMPLATE,
                input_dict={"node_text": node_txt},
                agent_name="page_index_node_summary",
                system_prompt=GENERATE_NODE_SUMMARY_SYSTEM_PROMPT,
            ),
            output_class=NodeSummaryResponse,
        )
        node_summary = llm_result.summary
    return node_summary


async def get_node_summary(
    node: dict[str, Any],
    llm_config: SelfHostedConfig,
    summary_token_threshold: int = 200,
) -> str:
    """Return a summary for a node, using the LLM only if the text exceeds the token threshold."""
    node_text: str = node.get("text", "")
    num_tokens = count_tokens(node_text)
    if num_tokens < summary_token_threshold:
        node_summary = node_text
    else:
        async with get_model_throttle("structure").acquire():
            node_summary = await generate_node_summary(node, llm_config)
    return node_summary


async def generate_summaries_for_structure_md(
    structure: dict[str, Any] | list[Any],
    summary_token_threshold: int,
    llm_config: SelfHostedConfig,
) -> dict[str, Any] | list[Any]:
    """Generate summaries for all nodes in the structure tree concurrently."""
    nodes = structure_to_list(structure)
    tasks = [
        get_node_summary(
            node,
            llm_config=llm_config,
            summary_token_threshold=summary_token_threshold,
        )
        for node in nodes
    ]
    summaries: list[str] = list(await asyncio.gather(*tasks))

    for node, summary in zip(nodes, summaries, strict=False):
        if not node.get("nodes"):
            node["summary"] = summary
        else:
            node["prefix_summary"] = summary
    return structure
