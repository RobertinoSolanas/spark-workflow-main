"""Entry point for starting the Plausibility Check workflow locally.

Reads project and document IDs from run_workflow_config.yaml (not committed).
Copy run_workflow_config.yaml.example to run_workflow_config.yaml and fill in
your IDs before running this script.
"""

import asyncio
import logging
from pathlib import Path
from uuid import uuid4

import yaml
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter

from src.config.env import ENV
from src.workflows.input_schemas import OrchestratorInputSchema
from src.workflows.orchestrator_workflow import PlausibilityMainOrchestratorWorkflow

logger = logging.getLogger(__name__)

_CONFIG_FILE = Path(__file__).parent / "run_workflow_config.yaml"


def _load_config() -> dict[str, str | list[str]]:
    if not _CONFIG_FILE.exists():
        raise FileNotFoundError(
            f"{_CONFIG_FILE} not found. "
            "Copy run_workflow_config.yaml.example to run_workflow_config.yaml and fill in your IDs."
        )
    with _CONFIG_FILE.open() as f:
        return yaml.safe_load(f)


async def main() -> None:
    """Start the plausibility workflow (worker must be running via main.py)."""
    cfg = _load_config()
    project_id = str(cfg["project_id"])
    document_ids = [str(d) for d in cfg["document_ids"]]
    classification_file_id = str(cfg["classification_file_id"]) if "classification_file_id" in cfg else None

    client = await Client.connect(
        ENV.TEMPORAL.HOST,
        data_converter=pydantic_data_converter,
    )

    workflow_id = f"check-plausibility-{uuid4()}"
    main_task_queue = ENV.TEMPORAL.TASK_QUEUE
    await client.start_workflow(
        PlausibilityMainOrchestratorWorkflow.run,
        OrchestratorInputSchema(
            project_id=project_id,
            document_ids=document_ids,
            classification_file_id=classification_file_id,
        ),
        id=workflow_id,
        task_queue=main_task_queue,
    )

    logger.info(
        "Workflow started: http://localhost:8080/namespaces/default/workflows/%s",
        workflow_id,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
