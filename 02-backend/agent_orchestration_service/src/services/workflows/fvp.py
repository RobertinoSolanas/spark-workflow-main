from datetime import timedelta
from typing import Any

from temporal.utils import WorkflowName, execute_workflow, start_workflow
from temporalio import activity, workflow
from temporalio.client import WorkflowHandle
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError
from temporalio.workflow import ChildWorkflowHandle

from src.config.settings import settings
from src.models.schemas.files import FileObject
from src.models.schemas.temporal.fvp import (
    DocumentTypeDefinition,
    FullFVPWorkflowInput,
    FVPWorkflowArgs,
    TemplateDocumentTypeResponse,
)
from src.services.activities.results import (
    send_fvp_results,
    send_plausibility_results,
    send_toc_matching_results,
)
from src.services.api_clients import FilesApiClient, FVPClient
from src.services.workflows.fvp_workflow import run_fvp_workflow


@activity.defn
async def get_template_document_types(
    project_id: str,
) -> list[TemplateDocumentTypeResponse]:
    return await FVPClient.get_template_document_types(project_id)


@activity.defn
async def get_project_files(project_id: str) -> list[FileObject]:
    return await FilesApiClient.list_files(project_id)


FVP_WORKFLOW_ID = WorkflowName("FVPWorkflow")
TASK_QUEUE = settings.temporal.task_queue


@workflow.defn(name=FVP_WORKFLOW_ID)
class FVPWorkflow:
    @workflow.run
    async def run(self, args: FVPWorkflowArgs) -> dict[str, Any]:
        workflow.logger.info(f"Starting FVPWorkflow for project: {args.project_id}")

        template_document_types = await workflow.execute_activity(
            get_template_document_types,
            args.project_id,
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                maximum_interval=timedelta(minutes=1),
            ),
        )

        project_files = await workflow.execute_activity(
            get_project_files,
            args.project_id,
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                maximum_interval=timedelta(minutes=1),
            ),
        )

        if not project_files:
            raise ApplicationError(
                f"No documents found for project {args.project_id}",
                non_retryable=True,
            )

        document_ids = [str(f.id) for f in project_files]

        workflow.logger.info(
            f"Found {len(project_files)} files for project {args.project_id}. Starting document processing workflow."
        )
        workflow.logger.info("Starting shared FVP extraction flow.")

        fvp_results = await run_fvp_workflow(
            FullFVPWorkflowInput(
                project_id=args.project_id,
                file_ids=document_ids,
                document_types=[
                    DocumentTypeDefinition(
                        category=doc_type.category,
                        document_type_name=doc_type.document_type_name,
                        document_type_description=doc_type.document_type_description,
                    )
                    for doc_type in template_document_types
                ],
            )
        )

        failed_branches: list[str] = []
        for result_item in fvp_results.results:
            if result_item.error or result_item.result is None:
                failed_branches.append(result_item.workflow_type)
                workflow.logger.error(
                    f"{result_item.workflow_type} failed for project {args.project_id}: {result_item.error}"
                )
                continue

            file_object = FileObject(**result_item.result)
            if result_item.workflow_type == "formalpruefung":
                await send_fvp_results(
                    project_id=args.project_id,
                    file_id=str(file_object.id),
                )
            elif result_item.workflow_type == "plausibilitaetspruefung":
                await send_plausibility_results(
                    project_id=str(file_object.project_id),
                    file_id=str(file_object.id),
                )
            elif result_item.workflow_type == "inhaltsverzeichnismatching":
                await send_toc_matching_results(
                    project_id=str(file_object.project_id),
                    file_id=str(file_object.id),
                )

        if failed_branches:
            raise ApplicationError(
                f"FVPWorkflow failed for project {args.project_id}: {', '.join(failed_branches)} failed",
                non_retryable=True,
            )
        return {
            "checks": [result.model_dump(mode="json") for result in fvp_results.results],
        }


async def execute_fvp_workflow(input: FVPWorkflowArgs, project_id: str | None = None) -> dict[str, Any]:
    return await execute_workflow(
        workflow_id=FVP_WORKFLOW_ID, input=input, task_queue=TASK_QUEUE, project_id=project_id
    )


async def start_fvp_workflow(
    input: FVPWorkflowArgs, project_id: str | None = None
) -> WorkflowHandle[Any, dict[str, Any]] | ChildWorkflowHandle[Any, dict[str, Any]]:
    return await start_workflow(workflow_id=FVP_WORKFLOW_ID, input=input, task_queue=TASK_QUEUE, project_id=project_id)
