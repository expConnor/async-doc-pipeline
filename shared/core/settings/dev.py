from .base import BaseAppSettings


class DevAppSettings(BaseAppSettings):
    log_level: str = "DEBUG"
    log_format: str = "pretty"
