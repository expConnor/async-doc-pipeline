from pathlib import Path

import pytest

from cli.commands import setup


class _Settings:
    def __init__(
        self,
        *,
        aws_region="us-east-1",
        s3_bucket="test-bucket",
        s3_endpoint_url=None,
        s3_access_key=None,
        s3_secret_key=None,
    ) -> None:
        self.aws_region = aws_region
        self.s3_bucket = s3_bucket
        self.s3_endpoint_url = s3_endpoint_url
        self.s3_access_key = s3_access_key
        self.s3_secret_key = s3_secret_key


# --- _ensure_bucket kwargs construction (mocked boto3, no real S3) ---


def test_ensure_bucket_minimal_settings_calls_client_with_region_only(mocker):
    mocker.patch("cli.commands.setup.get_settings", return_value=_Settings())
    client = mocker.MagicMock()
    boto_client = mocker.patch(
        "cli.commands.setup.boto3.client", return_value=client
    )

    setup._ensure_bucket()

    boto_client.assert_called_once_with("s3", region_name="us-east-1")
    client.create_bucket.assert_called_once_with(Bucket="test-bucket")


def test_ensure_bucket_with_endpoint_url_adds_path_style_config(mocker):
    mocker.patch(
        "cli.commands.setup.get_settings",
        return_value=_Settings(s3_endpoint_url="http://localhost:9000"),
    )
    client = mocker.MagicMock()
    boto_client = mocker.patch(
        "cli.commands.setup.boto3.client", return_value=client
    )

    setup._ensure_bucket()

    _, kwargs = boto_client.call_args
    assert kwargs["endpoint_url"] == "http://localhost:9000"
    assert kwargs["config"].s3["addressing_style"] == "path"


def test_ensure_bucket_with_credentials_passes_access_and_secret_key(mocker):
    mocker.patch(
        "cli.commands.setup.get_settings",
        return_value=_Settings(s3_access_key="access", s3_secret_key="secret"),
    )
    client = mocker.MagicMock()
    boto_client = mocker.patch(
        "cli.commands.setup.boto3.client", return_value=client
    )

    setup._ensure_bucket()

    _, kwargs = boto_client.call_args
    assert kwargs["aws_access_key_id"] == "access"
    assert kwargs["aws_secret_access_key"] == "secret"


# --- setup() orchestration (mocked collaborators) ---


@pytest.fixture
def order():
    return []


@pytest.fixture
def mocked_collaborators(mocker, order):
    ensure_bucket = mocker.patch(
        "cli.commands.setup._ensure_bucket",
        side_effect=lambda: order.append("ensure_bucket"),
    )
    migrate = mocker.patch(
        "cli.commands.setup.migrate",
        side_effect=lambda: order.append("migrate"),
    )

    async def _record_create_accounts(*args, **kwargs):
        order.append("create_accounts")

    create_accounts = mocker.patch(
        "cli.commands.setup.account._create_accounts",
        new=mocker.AsyncMock(side_effect=_record_create_accounts),
    )
    return ensure_bucket, migrate, create_accounts


def test_setup_calls_bucket_then_migrate_then_create_accounts_in_order(
    order, mocked_collaborators
):
    setup.setup()

    assert order == ["ensure_bucket", "migrate", "create_accounts"]


def test_setup_calls_create_accounts_with_count_1_and_default_csv_path(
    mocked_collaborators,
):
    _, _, create_accounts = mocked_collaborators

    setup.setup()

    create_accounts.assert_awaited_once_with(
        count=1, out=Path("local/accounts.csv")
    )


def test_setup_propagates_ensure_bucket_failure_and_skips_rest(
    mocked_collaborators,
):
    ensure_bucket, migrate, create_accounts = mocked_collaborators
    ensure_bucket.side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        setup.setup()

    migrate.assert_not_called()
    create_accounts.assert_not_awaited()


def test_setup_propagates_migrate_failure_and_skips_account_creation(
    mocked_collaborators,
):
    _, migrate, create_accounts = mocked_collaborators
    migrate.side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        setup.setup()

    create_accounts.assert_not_awaited()
