import s3fs

from src.config.settings import settings


def _create_s3fs() -> s3fs.S3FileSystem:
    """Create an S3FileSystem configured from application settings."""
    return s3fs.S3FileSystem(
        endpoint_url=settings.S3_ENDPOINT_URL,
        key=settings.S3_ACCESS_KEY_ID,
        secret=settings.S3_SECRET_ACCESS_KEY,
        client_kwargs=(
            {"region_name": settings.S3_REGION} if settings.S3_REGION else {}
        ),
        default_cache_type="none",
    )


def _get_s3_path(zip_path: str) -> str:
    """Build the full S3 object path from a relative zip_path."""
    return f"{settings.BUCKET_NAME}/{settings.DOC_STORE_PATH.rstrip('/')}/{zip_path}"
