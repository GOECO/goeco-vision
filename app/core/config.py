from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "GOECO Vision API"
    version: str = "0.1.0"
    debug: bool = False

    # PostgreSQL (Railway / Render) — thay bằng URL thật trong .env
    database_url: str = "sqlite+aiosqlite:///./goeco_vision.db"

    # YOLO local
    yolo_model: str = "yolov8n.pt"
    yolo_confidence_threshold: float = 0.5

    # AI model endpoint tuỳ chọn (để trống nếu dùng YOLO local)
    ai_model_endpoint: str = ""
    ai_model_api_key: str = ""

    # Camera stream
    camera_stream_base_url: str = ""

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60


settings = Settings()
