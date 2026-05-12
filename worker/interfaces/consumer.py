from abc import ABC, abstractmethod


class IMessageConsumer(ABC):
    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    def request_stop(self) -> None: ...
