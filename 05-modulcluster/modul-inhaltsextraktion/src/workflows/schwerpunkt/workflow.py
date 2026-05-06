# src/workflows/schwerpunkt/workflow.py
"""
Temporal workflow for Schwerpunktthema extraction.

Processes chunks in concurrent batches. Rate limiting is handled by the
shared process-level semaphore in concurrency.py, so all batches safely
compete for the same LLM concurrency slots.
"""

import asyncio
from typing import Any
from uuid import uuid4

from pydantic import BaseModel
from temporalio import workflow
from temporalio.client import Client, WorkflowHandle

from src.activities.schwerpunkt_extraction import (
    ProcessSchwerpunktBatchInput,
    process_schwerpunkt_batch,
)
from src.config import snapshot_config
from src.schemas import Chunk


class SchwerpunktWorkflowInput(BaseModel):
    chunks: list[Chunk]


class SchwerpunktWorkflowOutput(BaseModel):
    chunks: list[Chunk]
    added_metadata: bool


schwerpunkt_workflow_id = "schwerpunkt-workflow"


async def start_schwerpunkt(client: Client, input: SchwerpunktWorkflowInput) -> WorkflowHandle[Any, Any]:
    from src.env import ENV

    return await client.start_workflow(
        schwerpunkt_workflow_id,
        input,
        id=str(uuid4()),
        task_queue=ENV.TEMPORAL_TASK_QUEUE,
    )


async def execute_schwerpunkt(client: Client, input: SchwerpunktWorkflowInput) -> SchwerpunktWorkflowOutput:
    from src.env import ENV

    return await client.execute_workflow(
        schwerpunkt_workflow_id,
        input,
        id=str(uuid4()),
        task_queue=ENV.TEMPORAL_TASK_QUEUE,
    )


@workflow.defn(name=schwerpunkt_workflow_id)
class SchwerpunktWorkflow:
    """
    Workflow for extracting Schwerpunktthema metadata from document chunks.

    Processes chunks in concurrent batches. Rate limiting is handled by the
    shared process-level semaphore in concurrency.py, so all batches safely
    compete for the same LLM concurrency slots.
    """

    @workflow.run
    async def run(self, input: SchwerpunktWorkflowInput) -> SchwerpunktWorkflowOutput:
        cfg = snapshot_config()

        if not cfg.ENABLE_SCHWERPUNKTTHEMA_EXTRACTION:
            return SchwerpunktWorkflowOutput(chunks=input.chunks, added_metadata=False)

        batch_size = cfg.SCHWERPUNKT_BATCH_SIZE
        batches = [input.chunks[i : i + batch_size] for i in range(0, len(input.chunks), batch_size)]
        num_batches = len(batches)

        workflow.logger.info(
            f"Processing {len(input.chunks)} chunks for Schwerpunktthema in {num_batches} batches of {batch_size}"
        )

        if num_batches == 0:
            return SchwerpunktWorkflowOutput(chunks=input.chunks, added_metadata=False)

        batch_results = await asyncio.gather(
            *[
                process_schwerpunkt_batch(
                    ProcessSchwerpunktBatchInput(chunks=batch),
                    num_concurrent_batches=num_batches,
                )
                for batch in batches
            ]
        )

        updated_chunks: list[Chunk] = []
        for result in batch_results:
            updated_chunks.extend(result)

        workflow.logger.info(f"Schwerpunkt extraction completed for {len(updated_chunks)} chunks")
        return SchwerpunktWorkflowOutput(chunks=updated_chunks, added_metadata=True)
