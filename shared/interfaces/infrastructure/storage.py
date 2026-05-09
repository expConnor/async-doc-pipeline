from abc import ABC, abstractmethod


class IStorageService(ABC):
    @abstractmethod
    async def generate_upload_url(self, object_key: str) -> str: ...

    @abstractmethod
    async def generate_download_url(self, object_key: str) -> str: ...

    @abstractmethod
    async def object_exists(self, object_key: str) -> bool: ...

    @abstractmethod
    async def get_object(self, object_key: str) -> bytes: ...

    @abstractmethod
    async def put_object(self, object_key: str, content: bytes) -> None: ...
