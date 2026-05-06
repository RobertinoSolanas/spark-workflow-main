"""Hardcoded application config for manual tuning (dont use ENV. here)."""

from dataclasses import dataclass

from temporalio import workflow


@dataclass(frozen=True)
class Config:
    # Feature flags
    ENABLE_CACHING: bool = False
    ENABLE_SCHWERPUNKTTHEMA_EXTRACTION: bool = True
    ENABLE_HYPOTHETICAL_QUESTIONS: bool = True
    ENABLE_SPECIES_SCALE_EXTRACTION: bool = True

    # Timeouts
    DMS_TIMEOUT: int = 300
    VLM_TIMEOUT_SECONDS: int = 600
    VLM_ACTIVITY_TIMEOUT_MINUTES: int = 15
    VLM_MAX_TOKENS: int = 4096

    # Concurrency
    MAX_CONCURRENT_DMS_IMAGE_UPLOADS: int = 5
    LLM_STRUCTURED_OUTPUT_TEMPERATURE: float = 0.1
    SCHWERPUNKT_BATCH_SIZE: int = 15
    SCHWERPUNKT_WORKFLOW_BATCH_SIZE: int = 15
    SCHWERPUNKT_CLASSIFICATION_BATCH_SIZE: int = 5
    VLM_INPUTS_BATCH_SIZE: int = 15
    VLM_APPLY_BATCH_SIZE: int = 50
    VLM_SUMMARY_EXTRACTION_MAX_CHARS: int = 5000
    VLM_SUMMARY_DESCRIPTION_MAX_CHARS: int = 2000

    # Species/Scale Extraction Configuration
    SPECIES_SCALE_BATCH_SIZE: int = 30

    # Hypothetical Questions Configuration
    HYPOTHETICAL_QUESTIONS_BATCH_SIZE: int = 30

    SUMMARIZATION_BATCH_SIZE: int = 20
    SUMMARIZATION_WORKFLOW_BATCH_SIZE: int = 25
    SUMMARIZATION_CHUNK_MAX_CHARACTERS: int = 80000

    # Document handling & chunking
    ALLOWED_EXTENSIONS: tuple[str, ...] = (
        ".pdf",
        ".pptx",
        ".docx",
        ".xlsx",
        ".ppt",
        ".doc",
        ".xls",
        ".html",
        ".md",
        ".htm",
    )
    CHUNKING_MAX_CHARACTERS: int = 2000
    PARENT_CHUNK_MAX_CHARACTERS: int = 30000
    CHUNK_OVERLAP: int = 0
    PDF_SIZE_THRESHOLD_MB: int = 150
    PDF_PAGE_CHUNK_SIZE: int = 50

    # Adaptive PDF splitting
    PDF_TARGET_CHUNK_MB: int = 25
    PDF_FORCE_SPLIT_THRESHOLD_MB: int = 40

    # PDF image compression
    ENABLE_PDF_COMPRESSION: bool = True
    PDF_COMPRESSION_THRESHOLD_MB: int = 80
    PDF_COMPRESSION_MAX_IMAGE_DIMENSION: int = 1500
    PDF_COMPRESSION_JPEG_QUALITY: int = 65
    PDF_COMPRESSION_MIN_IMAGE_DIMENSION: int = 300
    PDF_COMPRESSION_MAX_IMAGE_PIXELS: int = 80_000_000  # PIL limit is ~89M

    # Raster fallback for docling-serve crashes on pages with huge embedded images
    ENABLE_RASTER_FALLBACK: bool = True
    RASTER_FALLBACK_DPI: int = 300
    RASTER_FALLBACK_JPEG_QUALITY: int = 90

    # Business logic
    SKIP_DOCUMENTS_BY_KEYWORDS: bool = True
    SKIPPED_DOCUMENT_KEYWORDS: tuple[str, ...] = (
        "Planfeststellungsbeschluss",
        "Planfeststellungsbesch",
        "PFB",
    )
    METADATA_PRIORITY_KEYWORDS: tuple[str, ...] = (
        "Erläuterungsbericht",
        "Erlaeuterungsbericht",
        "erlaeuterungsbericht",
        "erläuterungsbericht",
        "ErlB",
        "_EB",
        "EB_",
        " EB",
        "EB ",
    )
    BASE_METADATA_CHUNK_SIZE: int = 20000
    BASE_METADATA_TOTAL_LIMIT: int = 100000

    # Page dimensions for header/footer detection (A4 in points)
    PAGE_HEIGHT_POINTS: int = 842

    # Header/footer filtering configuration
    FILTER_HEADER_ZONE_RATIO: float = 0.12
    FILTER_FOOTER_ZONE_RATIO: float = 0.18
    FILTER_IMAGE_HASH_SIZE: int = 8
    FILTER_IMAGE_SIMILARITY_THRESHOLD: int = 8

    # Docling settings
    DOCLING_TIMEOUT: int = 1800
    DOCLING_OCR_ENGINE: str = "easyocr"
    DOCLING_OCR_LANG: tuple[str, ...] = ("de", "en")
    DOCLING_IMAGES_SCALE: float = 2.0
    DOCLING_TABLE_AS_HTML: bool = True
    DOCLING_TABLE_AS_IMAGE: bool = True
    TRUST_PROVIDER_LABELS_FOR_FILTER: bool = True
    DETECT_FULL_PAGE_IMAGES: bool = True
    FULL_PAGE_IMAGE_TEXT_COVERAGE_THRESHOLD: float = 0.10

    # Temporal workflow settings
    TEMPORAL_PROCESS_DOCUMENTS_SEQUENTIALLY: bool = True
    TEMPORAL_VLM_CHILD_WORKFLOW_BATCH_SIZE: int = 20
    EXTRACTION_CHUNK_CONCURRENCY: int = 3
    TEMPORAL_EXTRACTION_ACTIVITY_MAX_ATTEMPTS: int = 2
    TEMPORAL_LLM_ACTIVITY_MAX_ATTEMPTS: int = 5
    TEMPORAL_VLM_ACTIVITY_MAX_ATTEMPTS: int = 5
    TEMPORAL_STORAGE_ACTIVITY_MAX_ATTEMPTS: int = 3
    TEMPORAL_PROCESSING_ACTIVITY_MAX_ATTEMPTS: int = 2
    TEMPORAL_EXTERNAL_SERVICE_MAX_ATTEMPTS: int = 1
    TEMPORAL_PREPROCESSING_ACTIVITY_MAX_ATTEMPTS: int = 10
    TEMPORAL_QDRANT_ACTIVITY_MAX_ATTEMPTS: int = 3

    # VLM failure tolerance (fraction of elements allowed to fail)
    VLM_FAILURE_TOLERANCE: float = 0.2

    # Hallucination detection thresholds
    HALLUCINATION_MAX_LENGTH: int = 100000
    HALLUCINATION_TRUNCATE_LENGTH: int = 10000

    # Document retry loop (ProcessDocumentsWorkflow)
    DOCUMENT_RETRY_MAX_ATTEMPTS: int = 5
    DOCUMENT_RETRY_DELAY_SECONDS: int = 30
    DOCUMENT_FAILURE_RATE_THRESHOLD: float = 0.15  # 15% of docs, minimum 2
    DOCUMENT_FAILURE_MIN_ALLOWED: int = 2

    # Qdrant indexing
    QDRANT_PARALLEL_DOCS_SIZE: int = 10
    QDRANT_UPLOAD_BATCH_SIZE: int = 100


CONFIG_MEMO_KEY = "config_snapshot"


def _build_default() -> Config:
    from src.env import ENV

    return Config(
        DOCLING_OCR_ENGINE=ENV.DOCLING_OCR_ENGINE,
        EXTRACTION_CHUNK_CONCURRENCY=ENV.EXTRACTION_CHUNK_CONCURRENCY,
    )


_default = _build_default()


def snapshot_config() -> Config:
    """Snapshot config into the workflow memo.

    Must be called exactly once, at the very top of each workflow's run()
    method, before any activity or child-workflow scheduling.  On first
    execution it writes the current defaults into the memo; on replay it
    returns the previously snapshotted values so the workflow stays
    deterministic even if defaults change between deployments.
    """
    cfg = workflow.memo_value(CONFIG_MEMO_KEY, default=None, type_hint=Config)
    if cfg is not None:
        return cfg

    workflow.upsert_memo({CONFIG_MEMO_KEY: _default})
    return _default


def get_config() -> Config:
    """Get the application config (read-only).

    In workflow context: reads from the memo written by snapshot_config().
    Outside workflows (activities, tests, scripts): returns the module-level
    default.  Never writes to the memo — call snapshot_config() for that.
    """
    if not workflow.in_workflow():
        return _default

    cfg = workflow.memo_value(CONFIG_MEMO_KEY, default=None, type_hint=Config)
    if cfg is not None:
        return cfg

    return _default


def get_docling_url() -> str:
    """Build docling-serve API URL from protocol, host, and port."""
    from src.env import ENV

    return f"{ENV.DOCLING_PROTOCOL}://{ENV.DOCLING_HOST}:{ENV.DOCLING_PORT}"


def is_docling_provider() -> bool:
    """Check if the current extraction provider is Docling. Always True."""
    return True
