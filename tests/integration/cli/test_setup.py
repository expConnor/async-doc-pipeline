import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from cli.commands.setup import _ensure_bucket

BUCKET = "test-bucket"
REGION = "us-east-1"


class _Settings:
    def __init__(self) -> None:
        self.aws_region = REGION
        self.s3_bucket = BUCKET
        self.s3_endpoint_url = None
        self.s3_access_key = None
        self.s3_secret_key = None


@pytest.fixture(autouse=True)
def patched_settings(mocker):
    mocker.patch("cli.commands.setup.get_settings", return_value=_Settings())


def test_ensure_bucket_creates_bucket_when_absent():
    with mock_aws():
        _ensure_bucket()

        client = boto3.client("s3", region_name=REGION)
        client.head_bucket(Bucket=BUCKET)  # raises if bucket is missing


def test_ensure_bucket_swallows_bucket_already_owned_by_you():
    with mock_aws():
        _ensure_bucket()
        _ensure_bucket()  # must not raise on the second call


def test_ensure_bucket_reraises_other_client_errors(mocker):
    with mock_aws():
        client = boto3.client("s3", region_name=REGION)
        mocker.patch("cli.commands.setup.boto3.client", return_value=client)
        error = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "denied"}},
            "CreateBucket",
        )
        mocker.patch.object(client, "create_bucket", side_effect=error)

        with pytest.raises(ClientError):
            _ensure_bucket()
