from fastapi import APIRouter

from src.api.routes import approval_api, file_api, zip_file_api

api_router = APIRouter()

api_router.include_router(file_api.router)
api_router.include_router(approval_api.router)
api_router.include_router(zip_file_api.router)
