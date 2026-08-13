from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlmodel import Session, select

from models import ProjectTask, TaskStatus


def create_task(task_data: dict[str, Any], db: Session) -> ProjectTask:
    task = ProjectTask(**task_data)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_tasks_for_project(project_id: str, db: Session) -> list[ProjectTask]:
    return db.exec(
        select(ProjectTask).where(ProjectTask.project_id == project_id)
    ).all()


def get_task(task_id: str, db: Session) -> ProjectTask:
    task = db.get(ProjectTask, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    return task


def update_task(task_id: str, updated_data: dict[str, Any], db: Session) -> ProjectTask:
    task = db.get(ProjectTask, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    allowed_fields = {"title", "description", "assigned_to", "due_date", "status"}
    for field, value in updated_data.items():
        if field not in allowed_fields or value is None:
            continue
        if field == "status" and isinstance(value, str):
            value = TaskStatus(value)
        setattr(task, field, value)

    task.updated_at = datetime.now(timezone.utc)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def delete_task(task_id: str, db: Session) -> None:
    task = db.get(ProjectTask, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    # Delete related comments first to avoid FK nullify failure
    from models import ProjectTaskComment

    comments = db.exec(select(ProjectTaskComment).where(ProjectTaskComment.task_id == task_id)).all()
    for c in comments:
        db.delete(c)

    db.delete(task)
    db.commit()
