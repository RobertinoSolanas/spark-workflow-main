# ruff: noqa: E402
from temporal.observability import (
    ObservabilityConfig,
    setup_observability,
    shutdown_observability,
)

from src.config.env import ENV

setup_observability(
    ObservabilityConfig(
        service_name=ENV.OTEL_SERVICE_NAME,
        otel_endpoint=ENV.OTEL_ENDPOINT,
    )
)
import asyncio
import logging
import sys

from temporal.s3_payload_storage import S3PayloadStorage
from temporal.worker import start_temporal_worker

from src.activities.cluster_summarizer import build_clusters, summarize_cluster
from src.activities.context_checker import check_conflict
from src.activities.dms_activities import (
    aggregate_and_upload_checkpoints,
    fetch_erlauterungsbericht_document_ids,
    upload_temporal_checkpoint,
)
from src.activities.extraction_activities import (
    extract_claims_from_row_batch,
    extract_text_claims,
    parse_table_structure,
)
from src.activities.qdrant_activities import (
    delete_document_from_qdrant,
    embed_and_upload_claims,
    fetch_and_prepare_chunks,
    get_claim_ids,
    init_qdrant_collection,
)
from src.activities.risk_screener import build_screening_bundles_for_document, screen_claim_bundle
from src.config.config import config
from src.workflows.check_logic_wf.workflow import (
    PlausibilityCheckOrchestratorWorkflow,
    PlausibilityCheckSingleDocumentWorkflow,
)
from src.workflows.orchestrator_workflow import PlausibilityMainOrchestratorWorkflow
from src.workflows.qdrant_wf.workflow import (
    ClaimExtractionOrchestratorWorkflow,
    ClaimExtractionSingleDocumentWorkflow,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

llm_activities = [
    screen_claim_bundle,
    check_conflict,
    summarize_cluster,
    extract_text_claims,
    parse_table_structure,
    extract_claims_from_row_batch,
]

non_llm_activities = [
    upload_temporal_checkpoint,
    aggregate_and_upload_checkpoints,
    build_screening_bundles_for_document,
    build_clusters,
    # Qdrant pipeline activities
    get_claim_ids,
    init_qdrant_collection,
    delete_document_from_qdrant,
    fetch_and_prepare_chunks,
    embed_and_upload_claims,
    fetch_erlauterungsbericht_document_ids,
]

workflows = [
    PlausibilityCheckOrchestratorWorkflow,
    PlausibilityCheckSingleDocumentWorkflow,
    ClaimExtractionOrchestratorWorkflow,
    ClaimExtractionSingleDocumentWorkflow,
    PlausibilityMainOrchestratorWorkflow,
]


def _create_storage() -> S3PayloadStorage:
    return S3PayloadStorage(
        bucket_name=ENV.TEMPORAL.S3_BUCKET_NAME,
        endpoint_url=ENV.TEMPORAL.S3_ENDPOINT_URL,
        access_key=ENV.TEMPORAL.S3_ACCESS_KEY_ID,
        secret_key=ENV.TEMPORAL.S3_SECRET_ACCESS_KEY,
        region=ENV.TEMPORAL.S3_REGION,
    )


async def main() -> None:
    """
    Initialize and run two Temporal Workers in parallel.

    The main worker handles workflows and non-LLM activities on the base task queue.
    The LLM worker handles LLM activities on a dedicated '{base}-llm' task queue
    with limited concurrency to prevent overloading.
    """
    target_host = ENV.TEMPORAL.HOST
    task_queue = ENV.TEMPORAL.TASK_QUEUE
    llm_task_queue = ENV.TEMPORAL.TASK_QUEUE + config.LLM_TASK_QUEUE_SUFFIX

    logger.info("Initializing Temporal Worker Process...")
    logger.info(f"Target Temporal Host: {target_host}")
    logger.info(f"Main task queue: {task_queue}")
    logger.info(f"LLM task queue: {llm_task_queue}")
    logger.info(f"Registered Workflows: {len(workflows)}")
    logger.info(f"Non-LLM Activities: {len(non_llm_activities)}")
    logger.info(f"LLM Activities: {len(llm_activities)}")
    logger.info(
        f"LLM max concurrent activities: {config.TEMPORAL.LLM_MAX_CONCURRENT_ACTIVITIES}"
    )

    main_storage = _create_storage()
    llm_storage = _create_storage()

    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(
                start_temporal_worker(
                    host=target_host,
                    workflows=workflows,
                    activities=non_llm_activities,
                    task_queue=task_queue,
                    storage=main_storage,
                )
            )
            tg.create_task(
                start_temporal_worker(
                    host=target_host,
                    workflows=[],
                    activities=llm_activities,
                    task_queue=llm_task_queue,
                    storage=llm_storage,
                    max_concurrent_activities=config.TEMPORAL.LLM_MAX_CONCURRENT_ACTIVITIES,
                    max_task_queue_activities_per_second=ENV.TEMPORAL.LLM_MAX_PER_SECOND,
                )
            )
    except ExceptionGroup as eg:
        raise eg.exceptions[0] from eg
    else:
        logger.info("Temporal Workers stopped gracefully.")
    finally:
        shutdown_observability()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Received stop signal (KeyboardInterrupt). Shutting down...")
    except Exception:
        sys.exit(1)
