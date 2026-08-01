import csv
import hashlib
import stat

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import create_async_engine

from cli.commands.account import _create_accounts
from shared.infrastructure.models import Account


class _Settings:
    """Minimal settings stub — mirrors the one in test_container.py."""

    def __init__(self, db_url: str) -> None:
        self.sqlalchemy_engine_props = {"url": db_url}


@pytest.fixture(autouse=True)
def patched_settings(mocker, async_db_url):
    mocker.patch(
        "cli.commands.account.get_settings",
        return_value=_Settings(async_db_url),
    )


@pytest.fixture
async def cleanup_accounts(async_db_url):
    ids: list[int] = []
    yield ids
    if not ids:
        return
    engine = create_async_engine(async_db_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(delete(Account).where(Account.id.in_(ids)))
    finally:
        await engine.dispose()


def _read_csv_rows(path):
    with path.open(newline="") as f:
        return list(csv.reader(f))


async def _fetch_api_key_hash(async_db_url, account_id) -> str | None:
    engine = create_async_engine(async_db_url)
    try:
        async with engine.connect() as conn:
            return await conn.scalar(
                select(Account.api_key_hash).where(Account.id == account_id)
            )
    finally:
        await engine.dispose()


async def test_create_accounts_count_1_persists_row_and_writes_csv(
    tmp_path, async_db_url, cleanup_accounts
):
    out = tmp_path / "accounts.csv"

    await _create_accounts(count=1, out=out)

    rows = _read_csv_rows(out)
    assert rows[0] == ["account_id", "api_key"]
    assert len(rows) == 2

    account_id, api_key = int(rows[1][0]), rows[1][1]
    cleanup_accounts.append(account_id)

    api_key_hash = await _fetch_api_key_hash(async_db_url, account_id)
    assert api_key_hash == hashlib.sha256(api_key.encode()).hexdigest()


async def test_create_accounts_count_greater_than_one(
    tmp_path, async_db_url, cleanup_accounts
):
    out = tmp_path / "accounts.csv"

    await _create_accounts(count=5, out=out)

    rows = _read_csv_rows(out)
    assert rows[0] == ["account_id", "api_key"]
    data_rows = rows[1:]
    assert len(data_rows) == 5

    account_ids = [int(r[0]) for r in data_rows]
    api_keys = [r[1] for r in data_rows]
    assert len(set(account_ids)) == 5
    assert len(set(api_keys)) == 5

    cleanup_accounts.extend(account_ids)


async def test_create_accounts_csv_header_written_only_once_across_calls(
    tmp_path, cleanup_accounts
):
    out = tmp_path / "accounts.csv"

    await _create_accounts(count=1, out=out)
    await _create_accounts(count=1, out=out)

    rows = _read_csv_rows(out)
    header_rows = [r for r in rows if r == ["account_id", "api_key"]]
    assert len(header_rows) == 1
    assert len(rows) == 3  # 1 header + 2 data rows

    cleanup_accounts.extend(int(r[0]) for r in rows[1:])


async def test_create_accounts_chmod_0600(tmp_path, cleanup_accounts):
    out = tmp_path / "accounts.csv"

    await _create_accounts(count=1, out=out)

    mode = stat.S_IMODE(out.stat().st_mode)
    assert mode == 0o600

    cleanup_accounts.extend(int(r[0]) for r in _read_csv_rows(out)[1:])


async def test_create_accounts_creates_missing_parent_dir(
    tmp_path, cleanup_accounts
):
    out = tmp_path / "nested" / "does" / "not" / "exist" / "accounts.csv"

    await _create_accounts(count=1, out=out)

    assert out.exists()
    cleanup_accounts.extend(int(r[0]) for r in _read_csv_rows(out)[1:])
