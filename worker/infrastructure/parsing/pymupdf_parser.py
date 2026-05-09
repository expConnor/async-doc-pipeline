import asyncio
from typing import cast

import fitz
import pymupdf4llm

from ...interfaces.parser import IDocumentParser


class PyMuPDFParser(IDocumentParser):
    async def parse(self, content: bytes) -> str:
        return await asyncio.to_thread(self._parse_sync, content)

    @staticmethod
    def _parse_sync(content: bytes) -> str:
        doc = fitz.Document(stream=content, filetype="pdf")
        return cast(str, pymupdf4llm.to_markdown(doc))
