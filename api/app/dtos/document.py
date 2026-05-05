from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class DocumentDTO:
    id: int
    object_key: str
    account_id: int
    created_at: datetime


@dataclass(frozen=True)
class DocumentWithUploadUrlDTO:
    document: DocumentDTO
    upload_url: str


@dataclass(frozen=True)
class CreateDocumentDTO:
    object_key: str
    file_name: str
    account_id: int
