from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from models import ProjectStatus
from schemas.base import APIResponse


class CreateProjectRequest(BaseModel):
    name: str
    description: Optional[str] = None


class UpdateProjectRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[ProjectStatus] = None


class TransferProjectRequest(BaseModel):
    user_id: str


class ProjectResponse(APIResponse):
    id: str
    name: str
    description: Optional[str] = None
    status: ProjectStatus
    owner_id: str
    created_at: datetime
    updated_at: datetime