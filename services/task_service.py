from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlmodel import Session, select

from models import ProjectMember, ProjectMemberRole, ProjectTask, TaskStatus
from services.permissions import get_membership_or_404, require_role

OWNER_OR_ADMIN = {ProjectMemberRole.owner, ProjectMemberRole.admin}
CREATOR_ROLES = {ProjectMemberRole.owner, ProjectMemberRole.admin, ProjectMemberRole.member}


def _ensure_assignee_is_member(
    project_id: str, assigned_to: str, db: Session
) -> None:
    member = db.exec(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == assigned_to,
        )
    ).first()
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User is not a project member",
        )


def create_task(
    task_data: dict[str, Any], user_id: str, db: Session
) -> ProjectTask:
    require_role(db, task_data["project_id"], user_id, CREATOR_ROLES)

    assigned_to = task_data.get("assigned_to")
    if assigned_to:
        _ensure_assignee_is_member(task_data["project_id"], assigned_to, db)

    task = ProjectTask(**task_data)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_tasks_for_project(
    project_id: str, user_id: str, db: Session
) -> list[ProjectTask]:
    get_membership_or_404(db, project_id, user_id)
    return db.exec(
        select(ProjectTask).where(ProjectTask.project_id == project_id)
    ).all()


def get_task(task_id: str, user_id: str, db: Session) -> ProjectTask:
    task = db.get(ProjectTask, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    get_membership_or_404(db, task.project_id, user_id)
    return task


def update_task(
    task_id: str, user_id: str, updated_data: dict[str, Any], db: Session
) -> ProjectTask:
    task = db.get(ProjectTask, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    require_role(db, task.project_id, user_id, OWNER_OR_ADMIN)

    allowed_fields = {"title", "description", "assigned_to", "due_date", "status"}
    for field, value in updated_data.items():
        if field not in allowed_fields:
            continue
        if value is None and field != "assigned_to":
            continue
        if field == "assigned_to" and value:
            _ensure_assignee_is_member(task.project_id, value, db)
        if field == "status" and isinstance(value, str):
            value = TaskStatus(value)
        setattr(task, field, value)

    task.updated_at = datetime.now(timezone.utc)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def delete_task(task_id: str, user_id: str, db: Session) -> None:
    task = db.get(ProjectTask, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    require_role(db, task.project_id, user_id, OWNER_OR_ADMIN)

    # Related comments are removed via FK ON DELETE CASCADE
    db.delete(task)
    db.commit()