"""Account provisioning commands.

Generalizes local/create_account.py into a CLI command. Key generation
must stay byte-identical to the auth path in api/services/account.py:
secrets.token_urlsafe(32) hashed with hashlib.sha256(...).hexdigest().
"""

import asyncio
import csv
import hashlib
import secrets
from pathlib import Path

import typer
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from shared.core.config import get_settings
from shared.infrastructure.models import Account

app = typer.Typer(help="Manage accounts.")


async def _create_accounts(count: int, out: Path) -> None:
    settings = get_settings()
    engine = create_async_engine(**settings.sqlalchemy_engine_props)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    rows: list[tuple[int, str]] = []
    async with session_factory() as session:
        for _ in range(count):
            api_key = secrets.token_urlsafe(32)
            key_hash = hashlib.sha256(api_key.encode()).hexdigest()
            account = Account(api_key_hash=key_hash)
            session.add(account)
            await session.flush()
            rows.append((account.id, api_key))
        await session.commit()

    await engine.dispose()

    out.parent.mkdir(parents=True, exist_ok=True)
    write_header = not out.exists()
    with out.open("a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["account_id", "api_key"])
        writer.writerows(rows)

    print(f"created {count} account(s), wrote to {out}")


def create(
    count: int = typer.Option(1, min=1),
    out: Path = Path("local/accounts.csv"),
) -> None:
    asyncio.run(_create_accounts(count, out))


app.command("create")(create)
