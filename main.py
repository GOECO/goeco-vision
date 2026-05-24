import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.api.routes.health import router as health_router
from app.api.routes.deliveries import router as deliveries_router
from app.api.routes.shelves import router as shelves_router
from app.api.routes.shippers import router as shippers_router
from app.api.routes.dashboard import router as dashboard_router

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.database import init_db
    await init_db()
    logging.info("Database tables initialized.")
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description=(
        "GOECO Vision API — AI Camera Verification (YOLO + Face ID), "
        "Smart Shelf Inventory & Management Dashboard "
        "cho hạ tầng giao nhận thông minh tại chung cư đô thị."
    ),
    lifespan=lifespan,
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
app.include_router(shelves_router, prefix="/api/v1")
app.include_router(shippers_router, prefix="/api/v1")
app.include_router(dashboard_router)
