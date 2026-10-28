import json
import logging
import time
import uuid
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.api import auth, management, organizations, email_configuration, campaigns
from app.core.config import get_settings
from app.db.session import engine


class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({"time": self.formatTime(record), "level": record.levelname, "event": record.getMessage()})


handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logger = logging.getLogger("ntech")
logger.handlers = [handler]
logger.setLevel(logging.INFO)
settings = get_settings()


@asynccontextmanager
async def lifespan(app):
    from app.services.campaign_runtime import start_worker
    worker = start_worker() if settings.campaign_worker_enabled else None
    try:
        yield
    finally:
        if worker:
            await asyncio.to_thread(worker.stop)
        engine.dispose()


app = FastAPI(title="NTECH EMS API", version="0.1.0", lifespan=lifespan,
              docs_url="/api/docs" if settings.app_env != "production" else None,
              redoc_url=None, openapi_url="/api/openapi.json" if settings.app_env != "production" else None)
app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins, allow_credentials=True,
                   allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"], allow_headers=["Content-Type", "X-CSRF-Token"])


@app.middleware("http")
async def request_metadata(request: Request, call_next):
    request_id = uuid.uuid4().hex
    started = time.perf_counter()
    response = await call_next(request)
    response.headers.update({"X-Request-ID": request_id, "X-Content-Type-Options": "nosniff",
                             "Referrer-Policy": "same-origin", "Cache-Control": "no-store", "Pragma": "no-cache"})
    logger.info("%s %s status=%s elapsed_ms=%s request_id=%s", request.method, request.url.path,
                response.status_code, round((time.perf_counter()-started)*1000), request_id)
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Exclude rejected inputs: they can include passwords or enrollment secrets.
    return JSONResponse(status_code=422, content={"detail": "Please check the highlighted fields", "errors": [
        {"field": ".".join(str(p) for p in error["loc"][1:]), "message": error["msg"]} for error in exc.errors()]})


@app.exception_handler(IntegrityError)
async def conflict(request, exc):
    constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", "")
    message = {"organizations_normalized_name_key": "An organization with this name already exists, including archived records.",
               "users_email_key": "An account already uses this email address.",
               "uq_contact_org_email": "This organization already has a contact with this email address."}.get(constraint, "This change conflicts with an existing record. Refresh and try again.")
    return JSONResponse(status_code=409, content={"detail": message})


@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    logger.error("database_failure type=%s", type(exc).__name__)
    return JSONResponse(status_code=503, content={"detail": "The database is temporarily unavailable. Please try again."})


@app.exception_handler(Exception)
async def unexpected_error(request, exc):
    logger.error("unexpected_failure type=%s", type(exc).__name__)
    return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred. Please contact your administrator."})


@app.get("/api/health", tags=["Health"])
def health():
    database, schema = "unavailable", "unavailable"
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            database = "ready"
            revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
            schema = "ready" if revision == "0004_campaign_runtime" else "migration_required"
    except SQLAlchemyError:
        pass
    ready = database == schema == "ready"
    return JSONResponse(status_code=200 if ready else 503, content={"status": "ready" if ready else "not_ready", "application": "NTECH EMS", "version": "0.1.0", "database": database, "schema": schema})


for router in [auth.router, organizations.router, management.router, email_configuration.router, campaigns.router]:
    app.include_router(router, prefix="/api")
