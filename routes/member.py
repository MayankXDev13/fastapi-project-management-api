from fastapi import APIRouter, Depends
from sqlmodel import Session

from database import get_session
from deps import get_current_user
from models import User
from schemas.auth import MessageResponse
from schemas.member import (
    AddMemberRequest,
    MemberResponse,
    UpdateMemberRoleRequest,
)
from services.member_service import (
    add_member_to_project,
    get_project_members,
    remove_member_from_project,
    update_member_role,
)

router = APIRouter(prefix="/projects/{project_id}/members", tags=["members"])


def _to_response(member) -> MemberResponse:
    return MemberResponse(
        id=member.id,
        project_id=member.project_id,
        user_id=member.user_id,
        role=member.role,
        joined_at=member.joined_at,
        created_at=member.created_at,
        updated_at=member.updated_at,
    )


@router.get("", response_model=list[MemberResponse])
def list_members(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    return [_to_response(member) for member in get_project_members(project_id, current_user.id, db)]


@router.post("", response_model=MemberResponse, status_code=201)
def add_member_endpoint(
    project_id: str,
    body: AddMemberRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    member = add_member_to_project(project_id, body.user_id, current_user.id, db, body.role)
    return _to_response(member)


@router.put("/{user_id}", response_model=MemberResponse)
def update_member_role_endpoint(
    project_id: str,
    user_id: str,
    body: UpdateMemberRoleRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    member = update_member_role(project_id, user_id, current_user.id, body.new_role, db)
    return _to_response(member)


@router.delete("/{user_id}", response_model=MessageResponse)
def remove_member_endpoint(
    project_id: str,
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    remove_member_from_project(project_id, user_id, current_user.id, db)
    return MessageResponse(message="Member removed successfully")
