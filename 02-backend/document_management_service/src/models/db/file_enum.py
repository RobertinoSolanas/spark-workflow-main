from enum import Enum


class FileTypeEnum(str, Enum):
    DOCUMENT = "document"
    ZIP = "zip"
    TEMPLATE = "template"
    LAW_DATA = "law_data"
    CONTENT_EXTRACTION = "content_extraction"
    TEMPORAL_CHECKPOINT = "temporal_checkpoint"
