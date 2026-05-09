from pydantic import BaseModel


class CreateDocumentRequest(BaseModel):
    file_name: str
