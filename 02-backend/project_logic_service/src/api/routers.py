from fastapi import APIRouter

from src.api.routes import deadlines, generic_type, process_steps, project_type, projects

api_router = APIRouter()

api_router.include_router(deadlines.router)
api_router.include_router(generic_type.router)
api_router.include_router(process_steps.router)
api_router.include_router(project_type.router)
api_router.include_router(projects.router)
