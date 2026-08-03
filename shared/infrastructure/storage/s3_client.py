import asyncio

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from ...core.exceptions import StorageException
from ...interfaces.infrastructure.storage import IStorageService


class S3StorageService(IStorageService):
    def __init__(
        self,
        bucket: str,
        region: str,
        endpoint_url: str | None = None,
        public_endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
    ) -> None:
        self._bucket = bucket
        client_kwargs: dict = {"region_name": region}
        if endpoint_url is not None:
            client_kwargs["endpoint_url"] = endpoint_url
            client_kwargs["config"] = Config(
                s3={"addressing_style": "path"}, signature_version="s3v4"
            )
        if access_key is not None:
            client_kwargs["aws_access_key_id"] = access_key
            client_kwargs["aws_secret_access_key"] = secret_key
        self._client = boto3.client("s3", **client_kwargs)

        # Presigned URLs are handed to clients outside our network (browsers,
        # curl, the host machine), so they must be signed against a host those
        # clients can actually reach — not the internal Docker service name
        # used for direct get/put/head calls above. When no public endpoint is
        # configured (production, where S3 has one publicly reachable host),
        # reuse the same client.
        if public_endpoint_url is not None:
            presign_kwargs = {
                **client_kwargs,
                "endpoint_url": public_endpoint_url,
            }
            self._presign_client = boto3.client("s3", **presign_kwargs)
        else:
            self._presign_client = self._client

    async def generate_upload_url(self, object_key: str) -> str:
        try:
            return await asyncio.to_thread(
                self._presign_client.generate_presigned_url,
                "put_object",
                Params={"Bucket": self._bucket, "Key": object_key},
                ExpiresIn=3600,
            )
        except ClientError as e:
            raise StorageException() from e

    async def generate_download_url(self, object_key: str) -> str:
        try:
            return await asyncio.to_thread(
                self._presign_client.generate_presigned_url,
                "get_object",
                Params={"Bucket": self._bucket, "Key": object_key},
                ExpiresIn=3600,
            )
        except ClientError as e:
            raise StorageException() from e

    async def object_exists(self, object_key: str) -> bool:
        try:
            await asyncio.to_thread(
                self._client.head_object,
                Bucket=self._bucket,
                Key=object_key,
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise StorageException() from e

    async def get_object(self, object_key: str) -> bytes:
        try:
            response = await asyncio.to_thread(
                self._client.get_object,
                Bucket=self._bucket,
                Key=object_key,
            )
            return response["Body"].read()
        except ClientError as e:
            raise StorageException() from e

    async def put_object(self, object_key: str, content: bytes) -> None:
        try:
            await asyncio.to_thread(
                self._client.put_object,
                Bucket=self._bucket,
                Key=object_key,
                Body=content,
            )
        except ClientError as e:
            raise StorageException() from e
