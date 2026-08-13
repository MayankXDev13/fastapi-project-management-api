from datetime import datetime, timezone
from math import ceil
from typing import Optional

from fastapi import HTTPException, status
from sqlmodel import Session, select, func

from models import Project, ProjectMember, ProjectMemberRole
from services.permissions import get_membership_or_404, require_role

OWNER = {ProjectMemberRole.owner}
OWNER_OR_ADMIN = {ProjectMemberRole.owner, ProjectMemberRole.admin}


def create_project(
    name: str, description: Optional[str], owner_id: str, db: Session
) -> Project:
    project = Project(name=name, description=description, owner_id=owner_id)
    db.add(project)
    db.flush()

    member = ProjectMember(
        project_id=project.id,
        user_id=owner_id,
        role=ProjectMemberRole.owner,
    )
    db.add(member)
    db.commit()
    db.refresh(project)
    return project


def get_project(project_id: str, user_id: str, db: Session) -> Project:
    get_membership_or_404(db, project_id, user_id)
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    return project


def get_all_projects(
    db: Session,
    user_id: str,
    page: int = 1,
    page_size: int = 10,
    search: Optional[str] = None,
) -> dict:
    member_ids = select(ProjectMember.project_id).where(ProjectMember.user_id == user_id)
    query = select(Project).where(Project.id.in_(member_ids))
    count_query = select(func.count()).select_from(Project).where(
        Project.id.in_(member_ids)
    )

    if search:
        pattern = f"%{search}%"
        query = query.where(
            Project.name.ilike(pattern) | Project.description.ilike(pattern)
        )
        count_query = count_query.where(
            Project.name.ilike(pattern) | Project.description.ilike(pattern)
        )

    total = db.exec(count_query).one()
    total_pages = max(1, ceil(total / page_size))
    offset = (page - 1) * page_size

    projects = db.exec(query.offset(offset).limit(page_size)).all()

    return {
        "items": projects,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


def update_project(
    project_id: str, user_id: str, update_data: dict, db: Session
) -> Project:
    require_role(db, project_id, user_id, OWNER_OR_ADMIN)

    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    allowed_fields = {"name", "description", "status"}
    for field, value in update_data.items():
        if field in allowed_fields and value is not None:
            setattr(project, field, value)

    project.updated_at = datetime.now(timezone.utc)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def delete_project(project_id: str, user_id: str, db: Session) -> None:
    require_role(db, project_id, user_id, OWNER)

    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    # Related members, tasks and comments are removed via FK ON DELETE CASCADE
    db.delete(project)
    db.commit()


def transfer_project(
    project_id: str, new_owner_id: str, user_id: str, db: Session
) -> Project:
    actor_member = require_role(db, project_id, user_id, OWNER)

    if new_owner_id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already the project owner",
        )

    target_member = db.exec(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == new_owner_id,
        )
    ).first()
    if not target_member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User is not a project member",
        )

    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    project.owner_id = new_owner_id
    target_member.role = ProjectMemberRole.owner
    actor_member.role = ProjectMemberRole.member
    project.updated_at = datetime.now(timezone.utc)
    db.add(project)
    db.add(target_member)
    db.add(actor_member)
    db.commit()
    db.refresh(project)
    return project