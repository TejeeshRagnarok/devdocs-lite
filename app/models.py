from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=600)


class SearchResponseItem(BaseModel):
    path: str
    score: float
    language: str
    snippet: str


class PreviewResponse(BaseModel):
    path: str
    language: str
    content: str
    truncated: bool


class UploadResponse(BaseModel):
    message: str
    files_indexed: int
    project_name: str
