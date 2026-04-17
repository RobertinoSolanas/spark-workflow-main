from pydantic import BaseModel

from src.qdrant.schemas import ChunkPayload, ClaimPayload
from src.workflows.qdrant_wf.schemas.table_extraction import ParsedTable


class DocumentActivityInput(BaseModel):
    project_id: str
    document_id: str


class EmbedAndUploadInput(BaseModel):
    claims: list[ClaimPayload]


class ExtractTextClaimsInput(BaseModel):
    project_id: str
    document_id: str
    erlauterungsbericht: bool
    chunk: ChunkPayload


class ExtractClaimsFromRowBatchInput(BaseModel):
    project_id: str
    document_id: str
    erlauterungsbericht: bool
    table: ParsedTable
