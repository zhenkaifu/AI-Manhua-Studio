from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "AI Manhua Studio"
    api_prefix: str = "/api/v1"
    ollama_url: str = "http://localhost:11434/api/chat"
    model: str = "qwen3:4b"
    # 上传限制：10 MB，仅常见图片格式
    max_upload_bytes: int = 10 * 1024 * 1024
    allowed_image_types: tuple = ("image/png", "image/jpeg", "image/webp")

    class Config:
        env_prefix = "MANHUA_"


settings = Settings()
