import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.routes.health import router as health_router
from app.api.routes.deliveries import router as deliveries_router
from app.api.routes.shelves import router as shelves_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description=(
        "GOECO Vision API — AI Camera Verification System & Smart Shelf Inventory "
        "cho hạ tầng giao nhận thông minh tại chung cư đô thị."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    from app.database import init_db
    await init_db()
    logging.info("Database tables initialized.")


app.include_router(health_router)
app.include_router(deliveries_router, prefix="/api/v1")
app.include_router(shelves_router, prefix="/api/v1")
