from abc import ABC, abstractmethod


class IDocumentParser(ABC):
    @abstractmethod
    async def parse(self, content: bytes) -> str: ...
