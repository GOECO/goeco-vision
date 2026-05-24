from fastapi import APIRouter
from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.version,
    }


@router.get("/health/db")
async def db_health_check():
    from app.database import check_db_connection
    ok = await check_db_connection()
    return {
        "status": "ok" if ok else "error",
        "database": "connected" if ok else "unreachable",
        "url_hint": settings.database_url.split("@")[-1] if "@" in settings.database_url else "local",
    }
