from datetime import datetime, timezone
from math import ceil
from typing import Optional

from fastapi import HTTPException, status
from sqlmodel import Session, select, func

from models import Project, ProjectMember, ProjectMemberRole


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


def get_project(project_id: str, db: Session) -> Project:
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
    project_id: str, update_data: dict, db: Session
) -> Project:
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


def delete_project(project_id: str, db: Session) -> None:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    # Delete related members, tasks and comments to avoid FK / NOT NULL failures
    # (SQLModel Relationships without cascade try to nullify FKs)
    from models import ProjectTask, ProjectTaskComment

    members = db.exec(select(ProjectMember).where(ProjectMember.project_id == project_id)).all()
    for m in members:
        db.delete(m)

    tasks = db.exec(select(ProjectTask).where(ProjectTask.project_id == project_id)).all()
    for t in tasks:
        comments = db.exec(select(ProjectTaskComment).where(ProjectTaskComment.task_id == t.id)).all()
        for c in comments:
            db.delete(c)
        db.delete(t)

    db.delete(project)
    db.commit()
