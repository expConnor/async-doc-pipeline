from functools import lru_cache

from .settings.base import AppEnvTypes, BaseAppSettings
from .settings.dev import DevAppSettings
from .settings.test import TestAppSettings

_environments: dict[str, type[BaseAppSettings]] = {
    AppEnvTypes.production: BaseAppSettings,
    AppEnvTypes.development: DevAppSettings,
    AppEnvTypes.testing: TestAppSettings,
}


@lru_cache
def get_settings() -> BaseAppSettings:
    app_env = BaseAppSettings().app_env  # type: ignore[call-arg]
    return _environments[app_env]()  # type: ignore[call-arg]
