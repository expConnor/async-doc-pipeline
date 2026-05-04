from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class DocumentDTO:
    id: int
    object_key: str
    account_id: int
    created_at: datetime


@dataclass(frozen=True)
class CreateDocumentDTO:
    file_name: str
    account_id: int
