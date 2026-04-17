from fastapi import Depends
from sqlalchemy.ext.asyncio.session import AsyncSession

from src.models.db.database import get_db_session
from src.services.files.file_service import FileService
from src.services.zip_files.zip_file_service import ZipFileService
from src.utils.service_utils import create_file_service, create_zip_file_service


async def get_file_service(db: AsyncSession = Depends(get_db_session)) -> FileService:
    """
    Fastapi dependency for creating the file service.

    Args:
        db: Database session

    Returns:
        Instance of FileService
    """
    return await create_file_service(db)


async def get_zip_file_service(
    db: AsyncSession = Depends(get_db_session),
) -> ZipFileService:
    """
    Fastapi dependency for creating the zip file service.

    Args:
        db: Database session

    Returns:
        Instance of ZipFileService
    """
    return await create_zip_file_service(db)
