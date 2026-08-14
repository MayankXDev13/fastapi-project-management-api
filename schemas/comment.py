from datetime import datetime
from pydantic import BaseModel

from schemas.base import APIResponse


class CreateCommentRequest(BaseModel):
    comment: str


class UpdateCommentRequest(BaseModel):
    comment: str


class CommentResponse(APIResponse):
    id: str
    task_id: str
    user_id: str
    comment: str
    created_at: datetime
    updated_at: datetime
