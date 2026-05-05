from abc import ABC, abstractmethod


class IStorageService(ABC):
    @abstractmethod
    async def generate_upload_url(self, object_key: str) -> str: ...

    @abstractmethod
    async def generate_download_url(self, object_key: str) -> str: ...
