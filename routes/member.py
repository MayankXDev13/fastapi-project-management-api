from fastapi import APIRouter, Depends
from sqlmodel import Session

from database import get_session
from deps import get_current_user
from models import ProjectMember, User
from schemas.auth import MessageResponse
from schemas.member import (
    AddMemberRequest,
    MemberResponse,
    UpdateMemberRoleRequest,
)
from services.member_service import (
    add_member_to_project,
    remove_member_from_project,
    update_member_role,
)
from services.scope import PROJECT_SCOPE, scoped_list

router = APIRouter(prefix="/projects/{project_id}/members", tags=["members"])


@router.get("", response_model=list[MemberResponse])
def list_members(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    members = scoped_list(
        db, ProjectMember, current_user.id, PROJECT_SCOPE, project_id=project_id
    )
    return [MemberResponse.model_validate(member) for member in members]


@router.post("", response_model=MemberResponse, status_code=201)
def add_member_endpoint(
    project_id: str,
    body: AddMemberRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    member = add_member_to_project(project_id, body.user_id, current_user.id, db, body.role)
    return MemberResponse.model_validate(member)


@router.put("/{user_id}", response_model=MemberResponse)
def update_member_role_endpoint(
    project_id: str,
    user_id: str,
    body: UpdateMemberRoleRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    member = update_member_role(project_id, user_id, current_user.id, body.new_role, db)
    return MemberResponse.model_validate(member)


@router.delete("/{user_id}", response_model=MessageResponse)
def remove_member_endpoint(
    project_id: str,
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    remove_member_from_project(project_id, user_id, current_user.id, db)
    return MessageResponse(message="Member removed successfully")