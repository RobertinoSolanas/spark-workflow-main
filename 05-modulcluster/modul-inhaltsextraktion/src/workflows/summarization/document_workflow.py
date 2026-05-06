"""Child workflow wrapping the document-level summarization pipeline.

Extracts the batched summarization logic previously inlined in SingleDocumentWorkflow:
1. Split markdown by pages
2. Batch pages into SummarizationWorkflow children
3. Combine batch summaries into a final summary
"""

import asyncio
from datetime import timedelta

from pydantic import BaseModel
from temporalio import workflow
from temporalio.common import RetryPolicy

from src.activities.postprocessing import split_markdown_by_pages
from src.activities.summarization import CombineSummariesInput, _combine_summaries
from src.config import get_config, snapshot_config
from src.workflows.summarization.output_format import SummaryOutput
from src.workflows.summarization.workflow import (
    SummarizationWorkflow,
    SummarizationWorkflowInput,
)


class DocumentSummarizationWorkflowInput(BaseModel):
    markdown: str
    workflow_batch_size: int = 25  # pages per SummarizationWorkflow child


document_summarization_workflow_id = "document-summarization"


@workflow.defn(name=document_summarization_workflow_id)
class DocumentSummarizationWorkflow:
    @workflow.run
    async def run(self, input: DocumentSummarizationWorkflowInput) -> SummaryOutput:
        snapshot_config()
        # Split markdown by pages (activity to avoid blocking workflow thread)
        pages = await split_markdown_by_pages(input.markdown, pages_per_chunk=1)

        if not pages:
            return SummaryOutput(summary="")

        # Batch pages for child workflows
        batch_size = input.workflow_batch_size
        batches = ["\n".join(pages[i : i + batch_size]) for i in range(0, len(pages), batch_size)]

        workflow.logger.info(f"Running summarization in {len(batches)} batches ({len(pages)} pages total)")

        # Run batched child workflows in parallel
        batch_results = await asyncio.gather(
            *[
                workflow.execute_child_workflow(
                    SummarizationWorkflow.run,
                    SummarizationWorkflowInput(markdown=batch),
                    id=f"summarization-{workflow.info().workflow_id}-batch-{i}",
                    task_queue=workflow.info().task_queue,
                    task_timeout=timedelta(seconds=60),
                )
                for i, batch in enumerate(batches)
            ]
        )

        # Combine summaries from all batches
        summaries = [r.summary for r in batch_results if r.summary]

        if len(summaries) == 0:
            return SummaryOutput(summary="")
        if len(summaries) == 1:
            return SummaryOutput(summary=summaries[0])

        # Final combination via activity
        final_summary = await workflow.execute_activity(
            _combine_summaries,
            CombineSummariesInput(summaries=summaries, char_limit=3000),
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(
                maximum_attempts=get_config().TEMPORAL_LLM_ACTIVITY_MAX_ATTEMPTS,
            ),
        )
        return SummaryOutput(summary=final_summary)
