from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite+aiosqlite:///./satquery.db"
    clerk_jwks_url: str = ""
    clerk_issuer: str = ""
    clerk_audience: str = ""
    google_cloud_project: str = ""
    google_cloud_location: str = "us-central1"
    gcs_bucket: str = ""
    google_application_credentials: str = ""
    gemini_model: str = "gemini-3.6-flash"
    gemini_api_key: str = ""
    fusion_checkpoint_path: str = "checkpoints/fusion_model.pt"
    fusion_device: str = "cpu"
    # Final all-five-scenes S1/S2 water segmentation deployment model.
    water_segmentation_checkpoint_path: str = "checkpoints/optical_sar_water.pt"
    water_segmentation_device: str = "cpu"
    change_checkpoint_path: str = "checkpoints/best_model.pt"
    chat_context_message_limit: int = 20
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    local_classifier_path: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
