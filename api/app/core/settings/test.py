from pydantic_settings import SettingsConfigDict

from .base import BaseAppSettings


class TestAppSettings(BaseAppSettings):
    model_config = SettingsConfigDict(
        env_file=".env.test",
        extra="ignore",
    )
