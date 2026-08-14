from math import ceil
from typing import Optional

from fastapi import HTTPException, status
from sqlmodel import Session, select, func

from models import Project, ProjectMember, ProjectMemberRole
from persistence import get_or_404, remove, save, transaction
from services.permissions import Permission, authorize


def create_project(
    name: str, description: Optional[str], owner_id: str, db: Session
) -> Project:
    with transaction(db):
        project = Project(name=name, description=description, owner_id=owner_id)
        db.add(project)
        db.flush()

        member = ProjectMember(
            project_id=project.id,
            user_id=owner_id,
            role=ProjectMemberRole.owner,
        )
        db.add(member)
    return project


def get_project(project_id: str, user_id: str, db: Session) -> Project:
    authorize(db, user_id, Permission.project_view, project_id)
    return get_or_404(db, Project, project_id)


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
    ctx = authorize(db, user_id, Permission.project_update, project_id)

    allowed_fields = {"name", "description", "status"}
    for field, value in update_data.items():
        if field in allowed_fields and value is not None:
            setattr(ctx.project, field, value)

    return save(db, ctx.project)


def delete_project(project_id: str, user_id: str, db: Session) -> None:
    ctx = authorize(db, user_id, Permission.project_delete, project_id)
    # Related members, tasks and comments are removed via FK ON DELETE CASCADE
    remove(db, ctx.project)


def transfer_project(
    project_id: str, new_owner_id: str, user_id: str, db: Session
) -> Project:
    ctx = authorize(
        db,
        user_id,
        Permission.project_transfer,
        project_id,
        subject_id=new_owner_id,
    )

    with transaction(db):
        ctx.project.owner_id = new_owner_id
        ctx.subject.role = ProjectMemberRole.owner
        ctx.actor.role = ProjectMemberRole.member
    return ctx.project