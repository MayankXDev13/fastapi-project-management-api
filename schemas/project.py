from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from models import ProjectStatus


class CreateProjectRequest(BaseModel):
    name: str
    description: Optional[str] = None


class UpdateProjectRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[ProjectStatus] = None


class TransferProjectRequest(BaseModel):
    user_id: str


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    status: ProjectStatus
    owner_id: str
    created_at: datetime
    updated_at: datetime


class PaginatedProjectResponse(BaseModel):
    items: list[ProjectResponse]
    total: int
    page: int
    page_size: int
    total_pages: int