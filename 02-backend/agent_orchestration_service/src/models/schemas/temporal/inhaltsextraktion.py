from pydantic import BaseModel


class ProcessDocumentsWorkflowInputArgs(BaseModel):
    project_id: str
    file_ids: list[str]
