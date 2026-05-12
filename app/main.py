from __future__ import annotations

from contextlib import asynccontextmanager

import sentry_sdk
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from prometheus_client import make_asgi_app

from app.api.routes import approvals, chat, dashboard, health, meta, orchestrator, reports, shopify, whatsapp
from app.config import settings
from app.database import init_db
from app.redis_client import close_redis, get_redis

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.sentry_dsn and not settings.sentry_dsn.endswith("xxx"):
        sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment)

    await init_db()
    await get_redis()
    log.info("startup.complete", env=settings.environment)

    yield

    await close_redis()
    log.info("shutdown.complete")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else [],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Routers
app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(orchestrator.router, prefix="/orchestrator", tags=["orchestrator"])
app.include_router(approvals.router, prefix="/approvals", tags=["approvals"])
app.include_router(reports.router, prefix="/reports", tags=["reports"])
app.include_router(shopify.router, prefix="/shopify", tags=["shopify"])
app.include_router(meta.router, prefix="/meta", tags=["meta"])
app.include_router(whatsapp.router, prefix="/whatsapp", tags=["whatsapp"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
app.include_router(chat.router, prefix="/chat", tags=["chat"])

# Serve dashboard UI
@app.get("/ui", include_in_schema=False)
async def serve_dashboard():
    import pathlib
    html = pathlib.Path(__file__).parent.parent / "dashboard" / "index.html"
    return FileResponse(html)
