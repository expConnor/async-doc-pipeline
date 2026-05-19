from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnvTypes:
    """
    Available application environments.
    """

    production = "prod"
    development = "dev"
    testing = "test"


class BaseAppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )
    app_env: str = AppEnvTypes.production
    log_level: str = "INFO"
    log_format: str = "json"

    postgres_host: str
    postgres_port: int = 5432
    postgres_db: str
    postgres_user: str
    postgres_password: str

    rabbitmq_user: str
    rabbitmq_password: str
    rabbitmq_host: str = "localhost"
    rabbitmq_port: int = 5672
    rabbitmq_queue: str = "jobs"
    backpressure_threshold: int = 1000

    s3_bucket: str
    aws_region: str = "us-east-1"

    @computed_field
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field
    @property
    def rabbitmq_url(self) -> str:
        scheme = "amqps" if self.rabbitmq_port == 5671 else "amqp"
        return (
            f"{scheme}://{self.rabbitmq_user}:{self.rabbitmq_password}"
            f"@{self.rabbitmq_host}:{self.rabbitmq_port}/"
        )

    @computed_field
    @property
    def sqlalchemy_engine_props(self) -> dict:
        return {"url": self.database_url}
