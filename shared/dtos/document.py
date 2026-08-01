from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class DocumentDTO:
    id: UUID
    object_key: str
    file_name: str
    account_id: int
    created_at: datetime


@dataclass(frozen=True)
class DocumentWithUploadUrlDTO:
    document: DocumentDTO
    upload_url: str


@dataclass(frozen=True)
class CreateDocumentDTO:
    id: UUID
    object_key: str
    file_name: str
    account_id: int
