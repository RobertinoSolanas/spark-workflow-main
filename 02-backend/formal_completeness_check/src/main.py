from event_logging.middleware import EventLoggingMiddleware
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from src.api.middlewares.cors import add_cors
from src.api.middlewares.security_headers import SecurityHeadersMiddleware
from src.api.routes.fcs_api import router as fcs_router
from src.api.routes.probe_router import probe_router
from src.api.routes.template_management_api import router as template_management_router
from src.api.routes.toc_notes import router as toc_notes_router
from src.config.settings import settings
from src.exceptions.exception_handlers import register_exception_handlers
from src.utils.lifespan import lifespan

app = FastAPI(
    lifespan=lifespan,
)

# adds /metrics endpoint for Prometheus to scrape
Instrumentator().instrument(app).expose(app)

# Exception Handlers
register_exception_handlers(app=app)

app.include_router(probe_router)
app.include_router(fcs_router)
app.include_router(toc_notes_router)
app.include_router(template_management_router)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    EventLoggingMiddleware,
    service_name=settings.SERVICE_NAME,
    skip_paths=["/healthz", "/metrics"],
)
add_cors(app)
