from pydantic import BaseModel


class LLMMatchingWorkflowArgs(BaseModel):
    project_id: str
    document_types: list[dict]
