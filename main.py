import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.core.config import settings
from app.api.routes.health import router as health_router
from app.api.routes.auth import router as auth_router
from app.api.routes.deliveries import router as deliveries_router
from app.api.routes.shelves import router as shelves_router
from app.api.routes.shippers import router as shippers_router
from app.api.routes.notifications import router as notifications_router
from app.api.routes.agent import router as agent_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.ws import router as ws_router

logging.basicConfig(level=logging.INFO)

os.makedirs("uploads/verifications", exist_ok=True)
os.makedirs("uploads/shippers", exist_ok=True)

_templates = Jinja2Templates(directory="app/templates")


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
        "Smart Shelf Inventory, AI Operations Agent (Claude), "
        "JWT Auth & Management Dashboard "
        "cho hạ tầng giao nhận thông minh đô thị."
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
app.include_router(auth_router,          prefix="/api/v1")
app.include_router(deliveries_router,    prefix="/api/v1")
app.include_router(shelves_router,       prefix="/api/v1")
app.include_router(shippers_router,      prefix="/api/v1")
app.include_router(notifications_router, prefix="/api/v1")
app.include_router(agent_router,         prefix="/api/v1")
app.include_router(dashboard_router)
app.include_router(ws_router)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


@app.get("/verify", response_class=HTMLResponse)
@app.get("/verify/{delivery_id}", response_class=HTMLResponse)
async def verify_page(request: Request, delivery_id: int = None):
    return _templates.TemplateResponse(
        request, "verify.html", {"delivery_id": delivery_id}
    )
