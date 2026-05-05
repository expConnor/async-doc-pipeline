from abc import ABC, abstractmethod


class IMessagingService(ABC):
    @abstractmethod
    async def enqueue(self, queue: str, payload: dict) -> None: ...

    @abstractmethod
    async def queue_depth(self, queue: str) -> int: ...
