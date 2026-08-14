from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from models import TaskStatus
from schemas.base import APIResponse


class CreateTaskRequest(BaseModel):
    title: str
    description: Optional[str] = None
    assigned_to: Optional[str] = None
    due_date: Optional[datetime] = None
    status: Optional[TaskStatus] = None


class UpdateTaskRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    assigned_to: Optional[str] = None
    due_date: Optional[datetime] = None
    status: Optional[TaskStatus] = None


class TaskResponse(APIResponse):
    id: str
    project_id: str
    title: str
    description: Optional[str] = None
    assigned_to: Optional[str] = None
    created_by: str
    due_date: Optional[datetime] = None
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
