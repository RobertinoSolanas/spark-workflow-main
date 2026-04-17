"""Child workflow wrapping the Docling extraction pipeline."""

from temporalio import workflow

from src.schemas import ExtractionOutput
from src.services.docling_processing import (
    DoclingActivityInput,
    process_pdf_with_docling,
)

docling_extraction_workflow_id = "docling-extraction"


@workflow.defn(name=docling_extraction_workflow_id)
class DoclingExtractionWorkflow:
    @workflow.run
    async def run(self, input: DoclingActivityInput) -> ExtractionOutput:
        return await process_pdf_with_docling(input)
