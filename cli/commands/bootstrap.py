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

from alembic import command
from alembic.config import Config

from cli.commands import account


def migrate() -> None:
    command.upgrade(Config("alembic.ini"), "head")


def setup() -> None:
    migrate()
    asyncio.run(
        account._create_accounts(count=1, out=Path("local/accounts.csv"))
    )
