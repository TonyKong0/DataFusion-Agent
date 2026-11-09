from pydantic import BaseModel, Field, field_validator


class RagRequest(BaseModel):
    document_id: str | None = Field(default=None, min_length=1)
    document_ids: list[str] | None = None
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=10)

    @field_validator('question')
    @classmethod
    def trim_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError('empty question')
        return value
