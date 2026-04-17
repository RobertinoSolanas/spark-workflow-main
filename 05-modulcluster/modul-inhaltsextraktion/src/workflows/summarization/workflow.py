from datetime import timedelta
from typing import Any
from uuid import uuid4

from pydantic import BaseModel
from temporalio import workflow
from temporalio.client import Client, WorkflowHandle
from temporalio.common import RetryPolicy

from src.activities.postprocessing import split_markdown_by_pages
from src.activities.summarization import (
    CombineSummariesInput,
    _combine_summaries,
    _summarize_chunks_batch,
)
from src.config import snapshot_config
from src.workflows.summarization.output_format import SummaryOutput


class SummarizationWorkflowInput(BaseModel):
    markdown: str

    # Summarization parameters
    pages_per_chunk: int = 8
    threshold: int = 10000
    combine_size: int = 4
    char_limit: int = 3000


summarization_workflow_id = "summarization-workflow"


async def start_summarization(client: Client, input: SummarizationWorkflowInput) -> WorkflowHandle[Any, Any]:
    from src.env import ENV

    return await client.start_workflow(
        summarization_workflow_id,
        input,
        id=str(uuid4()),
        task_queue=ENV.TEMPORAL_TASK_QUEUE,
    )


async def execute_summarization(client: Client, input: SummarizationWorkflowInput) -> SummaryOutput:
    from src.env import ENV

    return await client.execute_workflow(
        summarization_workflow_id,
        input,
        id=str(uuid4()),
        task_queue=ENV.TEMPORAL_TASK_QUEUE,
    )


@workflow.defn(name=summarization_workflow_id)
class SummarizationWorkflow:
    @workflow.run
    async def run(self, input: SummarizationWorkflowInput) -> SummaryOutput:
        cfg = snapshot_config()
        workflow.logger.info("Starting SUMMARIZATION workflow")

        chunks = await split_markdown_by_pages(input.markdown, input.pages_per_chunk)

        total_chunks = len(chunks)

        if total_chunks == 0:
            workflow.logger.info("No chunks to summarize. Skipping summarization.")
            return SummaryOutput(summary="")

        workflow.logger.info(f"Processing {total_chunks} chunks for summarization")

        summaries: list[str] = []
        batch_size = cfg.SUMMARIZATION_BATCH_SIZE
        total_batches = (total_chunks + batch_size - 1) // batch_size
        for i in range(0, total_chunks, batch_size):
            batch = chunks[i : i + batch_size]
            workflow.logger.info(f"📦 Summarizing batch {i}/{total_batches}: chunks {i}-{i + batch_size - 1}")

            batch_summaries = await workflow.execute_activity(
                _summarize_chunks_batch,
                batch,
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=RetryPolicy(
                    maximum_attempts=cfg.TEMPORAL_LLM_ACTIVITY_MAX_ATTEMPTS,
                    initial_interval=timedelta(seconds=5),
                    backoff_coefficient=2,
                    maximum_interval=timedelta(minutes=1),
                ),
            )
            summaries.extend(batch_summaries)

        workflow.logger.info(f"Finished summarizing {total_chunks} chunks in {total_batches} batches")

        # 4. Iteratively reduce summaries if needed
        reduction_round = 0
        while sum(len(s) for s in summaries) > input.threshold and len(summaries) > 1:
            reduction_round += 1
            workflow.logger.info(
                f"Reduction round {reduction_round}: Total length ({sum(len(s) for s in summaries)}) "
                f"exceeds threshold. Combining {len(summaries)} summaries."
            )
            total_summaries = len(summaries)
            new_summaries: list[str] = []
            for i in range(0, total_summaries, input.combine_size):
                block = summaries[i : i + input.combine_size]

                combined = await workflow.execute_activity(
                    _combine_summaries,
                    CombineSummariesInput(summaries=block, char_limit=999999),
                    start_to_close_timeout=timedelta(minutes=10),
                    retry_policy=RetryPolicy(
                        maximum_attempts=cfg.TEMPORAL_LLM_ACTIVITY_MAX_ATTEMPTS,
                    ),
                )
                new_summaries.append(combined)

            summaries = new_summaries
            workflow.logger.info(f"Reduction complete. New summary count: {len(summaries)}")

        # 5. Final combination and optional condensation
        final_summary = await workflow.execute_activity(
            _combine_summaries,
            CombineSummariesInput(summaries=summaries, char_limit=input.char_limit),
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(
                maximum_attempts=cfg.TEMPORAL_LLM_ACTIVITY_MAX_ATTEMPTS,
            ),
        )

        workflow.logger.info(f"✅ Summarization workflow (DMS) completed ({len(final_summary)} chars)")
        return SummaryOutput(summary=final_summary)
