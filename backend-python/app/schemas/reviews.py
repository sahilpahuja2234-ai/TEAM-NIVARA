"""Pydantic schemas for review endpoints."""

from pydantic import BaseModel, Field


class CreateReviewRequest(BaseModel):
    book_id: int
    rating: int = Field(ge=1, le=5)
    body: str = ""
