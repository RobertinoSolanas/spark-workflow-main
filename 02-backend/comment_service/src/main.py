from event_logging.middleware import EventLoggingMiddleware
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from src.api.middlewares.cors import add_cors
from src.api.middlewares.security_headers import SecurityHeadersMiddleware
from src.api.routes.comment_route import router as comment_router
from src.api.routes.probe_router import probe_router
from src.config.settings import settings
from src.exceptions.exception_handlers import register_exception_handlers
from src.utils.lifespan import lifespan

app = FastAPI(lifespan=lifespan)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    EventLoggingMiddleware,
    service_name=settings.SERVICE_NAME,
    skip_paths=["/healthz", "/metrics"],
)
add_cors(app)

Instrumentator().instrument(app).expose(app)

register_exception_handlers(app)

app.include_router(comment_router)
app.include_router(probe_router)
