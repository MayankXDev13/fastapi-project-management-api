from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlmodel import Session, select, update

from models import ProjectMember, ProjectMemberRole, ProjectTask
from services.permissions import get_membership_or_404, require_role

OWNER_OR_ADMIN = {ProjectMemberRole.owner, ProjectMemberRole.admin}


def get_project_members(
    project_id: str, user_id: str, db: Session
) -> list[ProjectMember]:
    get_membership_or_404(db, project_id, user_id)
    return db.exec(
        select(ProjectMember).where(ProjectMember.project_id == project_id)
    ).all()


def add_member_to_project(
    project_id: str,
    user_id: str,
    actor_id: str,
    db: Session,
    role: ProjectMemberRole = ProjectMemberRole.member,
) -> ProjectMember:
    require_role(db, project_id, actor_id, OWNER_OR_ADMIN)

    if role == ProjectMemberRole.owner:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Owner role can only be granted via project transfer",
        )

    existing = db.exec(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a project member",
        )

    member = ProjectMember(project_id=project_id, user_id=user_id, role=role)
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def update_member_role(
    project_id: str,
    target_user_id: str,
    actor_id: str,
    new_role: ProjectMemberRole | str,
    db: Session,
) -> ProjectMember:
    require_role(db, project_id, actor_id, OWNER_OR_ADMIN)

    member = db.exec(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == target_user_id,
        )
    ).first()
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project member not found",
        )

    if member.role == ProjectMemberRole.owner:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Owner role can only be changed via project transfer",
        )

    new_role = ProjectMemberRole(new_role) if isinstance(new_role, str) else new_role
    if new_role == ProjectMemberRole.owner:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Owner role can only be granted via project transfer",
        )

    member.role = new_role
    member.updated_at = datetime.now(timezone.utc)
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def remove_member_from_project(
    project_id: str, target_user_id: str, actor_id: str, db: Session
) -> None:
    require_role(db, project_id, actor_id, OWNER_OR_ADMIN)

    member = db.exec(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == target_user_id,
        )
    ).first()
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project member not found",
        )
    if member.role == ProjectMemberRole.owner:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Owner cannot be removed; transfer ownership first",
        )

    db.exec(
        update(ProjectTask)
        .where(
            ProjectTask.project_id == project_id,
            ProjectTask.assigned_to == target_user_id,
        )
        .values(assigned_to=None)
    )
    db.delete(member)
    db.commit()