from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "GOECO Vision API"
    version: str = "0.1.0"
    debug: bool = False

    database_url: str = "sqlite+aiosqlite:///./goeco_vision.db"

    # TODO: configure AI model endpoint (e.g. Google Vision AI, custom YOLO)
    ai_model_endpoint: str = ""
    ai_model_api_key: str = ""

    # TODO: configure camera stream sources (RTSP URLs per building/floor)
    camera_stream_base_url: str = ""

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    class Config:
        env_file = ".env"


settings = Settings()
