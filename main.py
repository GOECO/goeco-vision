from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.routes.health import router as health_router
from app.api.routes.deliveries import router as deliveries_router

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="AI Camera Verification System for GOECO smart delivery infrastructure",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(deliveries_router, prefix="/api/v1")
