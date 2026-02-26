"""
LeaseTeq Risk Engine — FastAPI Application Entry Point

POST /v1/risk/evaluate  → synchronous scoring
GET  /v1/risk/health     → health check
GET  /docs               → OpenAPI / Swagger UI
"""
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from app.api.risk_endpoint import router as risk_router
from app.api.admin_endpoint import router as admin_router
from app.core.config import get_settings

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.ConsoleRenderer() if get_settings().app_env == "development"
        else structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(get_settings().log_level),
)
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("risk_engine_starting", model_version=get_settings().scoring_model_version)
    yield
    logger.info("risk_engine_shutting_down")


app = FastAPI(
    title="LeaseTeq Risk Engine",
    description="Real-time credit scoring microservice for lease applications",
    version="1.2.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS (Flowable + internal tools) ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_methods=["POST", "GET", "PUT", "DELETE"],
    allow_headers=["*"],
)

# ── Prometheus metrics ──
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# ── Routes ──
app.include_router(risk_router)
app.include_router(admin_router)


@app.get("/", include_in_schema=False)
async def root():
    return {
        "service": "lt-risk-engine",
        "version": "1.2.0",
        "docs": "/docs",
        "evaluate": "POST /v1/risk/evaluate",
    }
