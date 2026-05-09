import asyncio

import boto3
from botocore.exceptions import ClientError

from ...core.exceptions import StorageException
from ...interfaces.infrastructure.storage import IStorageService


class S3StorageService(IStorageService):
    def __init__(self, bucket: str, region: str) -> None:
        self._bucket = bucket
        self._client = boto3.client("s3", region_name=region)

    async def generate_upload_url(self, object_key: str) -> str:
        try:
            return await asyncio.to_thread(
                self._client.generate_presigned_url,
                "put_object",
                Params={"Bucket": self._bucket, "Key": object_key},
                ExpiresIn=3600,
            )
        except ClientError as e:
            raise StorageException() from e

    async def generate_download_url(self, object_key: str) -> str:
        try:
            return await asyncio.to_thread(
                self._client.generate_presigned_url,
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
