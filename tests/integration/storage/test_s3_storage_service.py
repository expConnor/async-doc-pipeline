import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from shared.core.exceptions import StorageException
from shared.infrastructure.storage.s3_client import S3StorageService

BUCKET = "test-bucket"
REGION = "us-east-1"


@pytest.fixture
def s3_service():
    with mock_aws():
        boto3.client("s3", region_name=REGION).create_bucket(Bucket=BUCKET)
        service = S3StorageService(bucket=BUCKET, region=REGION)
        yield service


async def test_object_exists_present(s3_service):
    s3_service._client.put_object(Bucket=BUCKET, Key="test.pdf", Body=b"data")

    assert await s3_service.object_exists("test.pdf") is True


async def test_object_exists_absent(s3_service):
    assert await s3_service.object_exists("missing.pdf") is False


async def test_object_exists_non_404_raises_storage_exception(
    s3_service, mocker
):
    error = ClientError(
        {"Error": {"Code": "403", "Message": "Forbidden"}}, "HeadObject"
    )
    mocker.patch.object(s3_service._client, "head_object", side_effect=error)

    with pytest.raises(StorageException):
        await s3_service.object_exists("any.pdf")


async def test_get_object_success(s3_service):
    s3_service._client.put_object(Bucket=BUCKET, Key="doc.pdf", Body=b"content")

    data = await s3_service.get_object("doc.pdf")

    assert data == b"content"


async def test_get_object_missing_raises_storage_exception(s3_service):
    with pytest.raises(StorageException):
        await s3_service.get_object("nonexistent.pdf")


async def test_put_object_success(s3_service):
    await s3_service.put_object("output.md", b"# Hello")

    response = s3_service._client.get_object(Bucket=BUCKET, Key="output.md")
    assert response["Body"].read() == b"# Hello"


async def test_put_object_client_error_raises_storage_exception(
    s3_service, mocker
):
    error = ClientError(
        {"Error": {"Code": "500", "Message": "Internal Error"}}, "PutObject"
    )
    mocker.patch.object(s3_service._client, "put_object", side_effect=error)

    with pytest.raises(StorageException):
        await s3_service.put_object("fail.md", b"data")


async def test_generate_upload_url_success(s3_service):
    url = await s3_service.generate_upload_url("uploads/doc.pdf")

    assert isinstance(url, str)
    assert len(url) > 0
    assert "doc.pdf" in url


async def test_generate_upload_url_client_error_raises_storage_exception(
    s3_service, mocker
):
    error = ClientError(
        {"Error": {"Code": "500", "Message": "Error"}}, "GeneratePresignedUrl"
    )
    mocker.patch.object(
        s3_service._client, "generate_presigned_url", side_effect=error
    )

    with pytest.raises(StorageException):
        await s3_service.generate_upload_url("uploads/doc.pdf")


async def test_generate_download_url_success(s3_service):
    url = await s3_service.generate_download_url("artifacts/1/doc.md")

    assert isinstance(url, str)
    assert len(url) > 0
    assert "doc.md" in url


async def test_generate_download_url_client_error_raises_storage_exception(
    s3_service, mocker
):
    error = ClientError(
        {"Error": {"Code": "500", "Message": "Error"}}, "GeneratePresignedUrl"
    )
    mocker.patch.object(
        s3_service._client, "generate_presigned_url", side_effect=error
    )

    with pytest.raises(StorageException):
        await s3_service.generate_download_url("artifacts/1/doc.md")
