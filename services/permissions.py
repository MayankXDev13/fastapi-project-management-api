from fastapi import HTTPException, status
from sqlmodel import Session, select

from models import ProjectMember, ProjectMemberRole


def get_membership_or_404(
    db: Session, project_id: str, user_id: str
) -> ProjectMember:
    member = db.exec(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    ).first()
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    return member


def require_role(
    db: Session,
    project_id: str,
    user_id: str,
    allowed_roles: set[ProjectMemberRole],
) -> ProjectMember:
    member = get_membership_or_404(db, project_id, user_id)
    if member.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    return member