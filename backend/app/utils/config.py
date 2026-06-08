from functools import cached_property

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    app_base_url: str = "http://127.0.0.1:8000"
    storage_dir: str = "storage"
    crawl_max_pages: int = 6
    crawl_timeout_seconds: int = 18
    allow_playwright: bool = True
    cors_origins: str = "chrome-extension://*,http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @cached_property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
