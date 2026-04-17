import asyncio

from pydantic import BaseModel
from temporalio import activity

from src.activities.llm_invoke import LlmInvokeInput, llm_invoke_structured_direct
from src.concurrency import get_model_throttle
from src.models.model_manager import SelfHostedConfig
from src.workflows.summarization.output_format import SummaryOutput
from src.workflows.summarization.prompt import (
    FINAL_OVERVIEW_SYSTEM_PROMPT,
    FINAL_OVERVIEW_USER_TEMPLATE,
    INITIAL_SUMMARY_SYSTEM_PROMPT,
    INITIAL_SUMMARY_USER_TEMPLATE,
)


class CombineSummariesInput(BaseModel):
    summaries: list[str]
    char_limit: int


@activity.defn(name="combine_summaries")
async def _combine_summaries(input: CombineSummariesInput) -> str:
    """
    Combines multiple summaries into a final summary.

    If the combined text exceeds char_limit, it runs a final condensation LLM call.
    """
    summaries = input.summaries
    char_limit = input.char_limit
    complete_summary = "\n".join(summaries)

    # If already short enough, return as-is
    if len(complete_summary) <= char_limit:
        activity.logger.info(f"Combined summary within limit ({len(complete_summary)} chars)")
        return complete_summary

    # Run final condensation
    activity.logger.info(f"Combined summary exceeds limit ({len(complete_summary)} > {char_limit}). Condensing.")

    async with get_model_throttle("summarization").acquire():
        llm_config: SelfHostedConfig = {
            "provider": "self_hosted",
            "model_name": "summarization",
        }

        result = await llm_invoke_structured_direct(
            input=LlmInvokeInput(
                llm_config=llm_config,
                prompt_template=FINAL_OVERVIEW_USER_TEMPLATE,
                input_dict={"complete_summary": complete_summary},
                agent_name="summarization.final",
                system_prompt=FINAL_OVERVIEW_SYSTEM_PROMPT,
            ),
            output_class=SummaryOutput,
        )

    activity.logger.info(f"Final summary condensed to {len(result.summary)} chars")
    return result.summary


# --- DMS-specific Activities ---


@activity.defn(name="summarize_chunks_batch")
async def _summarize_chunks_batch(
    chunks: list[str],
) -> list[str]:
    async def summarize_single(chunk_content: str, idx: int) -> str:
        async with get_model_throttle("summarization").acquire():
            llm_config: SelfHostedConfig = {
                "provider": "self_hosted",
                "model_name": "summarization",
            }

            result = await llm_invoke_structured_direct(
                input=LlmInvokeInput(
                    llm_config=llm_config,
                    prompt_template=INITIAL_SUMMARY_USER_TEMPLATE,
                    input_dict={"content": chunk_content},
                    agent_name="summarization.chunk",
                    system_prompt=INITIAL_SUMMARY_SYSTEM_PROMPT,
                ),
                output_class=SummaryOutput,
            )
            return result.summary

    # Process all chunks in batch concurrently (limited by semaphore)
    tasks = [summarize_single(chunk, i) for i, chunk in enumerate(chunks)]
    summaries = await asyncio.gather(*tasks)

    activity.logger.info(f"Batch complete: {len(summaries)} chunks summarized")
    return list(summaries)
