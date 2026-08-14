from datetime import datetime

from pydantic import BaseModel

from models import ProjectMemberRole
from schemas.base import APIResponse


class AddMemberRequest(BaseModel):
    user_id: str
    role: ProjectMemberRole = ProjectMemberRole.member


class UpdateMemberRoleRequest(BaseModel):
    new_role: ProjectMemberRole


class MemberResponse(APIResponse):
    id: str
    project_id: str
    user_id: str
    role: ProjectMemberRole
    joined_at: datetime
    created_at: datetime
    updated_at: datetime
