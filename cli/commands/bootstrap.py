"""Bootstrap commands (migrate, setup).

`migrate()` and `setup()` are both plain `def`, never `async def`. Alembic's
`command.upgrade()` runs `shared/migrations/env.py`, whose last line is
`asyncio.run(run_migrations_online())` — so `command.upgrade()` opens and
closes its own event loop internally on every call. `_create_accounts()`
(from `cli/commands/account.py`) is `async def` and needs its own
`asyncio.run()`. If `setup()` were `async def` and awaited both, the first
`asyncio.run()` inside `env.py` would be called while `setup()`'s own outer
loop is already running, raising
`RuntimeError: asyncio.run() cannot be called from a running event loop`.
Keeping both functions synchronous and sequential — migrate() fully opens
and closes its loop before setup() starts a second, separate loop for
account creation — avoids this entirely.
"""

import asyncio
from pathlib import Path

import boto3
from alembic import command
from alembic.config import Config
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from cli.commands import account
from shared.core.config import get_settings


def _ensure_bucket() -> None:
    settings = get_settings()
    client_kwargs: dict = {"region_name": settings.aws_region}
    if settings.s3_endpoint_url is not None:
        client_kwargs["endpoint_url"] = settings.s3_endpoint_url
        client_kwargs["config"] = BotoConfig(s3={"addressing_style": "path"})
    if settings.s3_access_key is not None:
        client_kwargs["aws_access_key_id"] = settings.s3_access_key
        client_kwargs["aws_secret_access_key"] = settings.s3_secret_key
    client = boto3.client("s3", **client_kwargs)

    try:
        client.create_bucket(Bucket=settings.s3_bucket)
    except ClientError as e:
        if e.response["Error"]["Code"] != "BucketAlreadyOwnedByYou":
            raise


def migrate() -> None:
    command.upgrade(Config("alembic.ini"), "head")


def setup() -> None:
    _ensure_bucket()
    migrate()
    asyncio.run(
        account._create_accounts(count=1, out=Path("local/accounts.csv"))
    )
