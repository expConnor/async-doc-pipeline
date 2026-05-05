from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnvTypes:
    """
    Available application environments.
    """

    production = "prod"
    testing = "test"


class BaseAppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )
    app_env: str = AppEnvTypes.production

    postgres_host: str
    postgres_port: int = 5432
    postgres_db: str
    postgres_user: str
    postgres_password: str

    rabbitmq_user: str
    rabbitmq_password: str
    rabbitmq_host: str = "localhost"
    rabbitmq_port: int = 5672

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
        return (
            f"amqp://{self.rabbitmq_user}:{self.rabbitmq_password}"
            f"@{self.rabbitmq_host}:{self.rabbitmq_port}/"
        )

    @computed_field
    @property
    def sqlalchemy_engine_props(self) -> dict:
        return {"url": self.database_url}
