from fastapi import HTTPException, status
from sqlmodel import Session, select

from models import ProjectMember, ProjectMemberRole, ProjectTask, TaskStatus
from persistence import remove, save
from schemas.base import build_entity
from schemas.task import CreateTaskRequest, UpdateTaskRequest
from services.permissions import Permission, authorize
from services.scope import PROJECT_SCOPE, scoped_get


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
    project_id: str,
    body: CreateTaskRequest,
    user_id: str,
    db: Session,
) -> ProjectTask:
    authorize(
        db,
        user_id,
        Permission.task_create,
        project_id,
        subject_id=body.assigned_to,
    )

    return save(
        db,
        build_entity(
            ProjectTask,
            body,
            project_id=project_id,
            created_by=user_id,
        ),
    )


def update_task(
    project_id: str,
    task_id: str,
    body: UpdateTaskRequest,
    user_id: str,
    db: Session,
) -> ProjectTask:
    task = scoped_get(
        db, ProjectTask, task_id, user_id, PROJECT_SCOPE, project_id=project_id
    )
    authorize(db, user_id, Permission.task_update, project_id)

    for field, value in body.model_dump(exclude_unset=True).items():
        if value is None and field != "assigned_to":
            continue
        if field == "assigned_to" and value:
            _ensure_assignee_is_member(project_id, value, db)
        if field == "status" and isinstance(value, str):
            value = TaskStatus(value)
        setattr(task, field, value)

    return save(db, task)


def delete_task(
    project_id: str, task_id: str, user_id: str, db: Session
) -> None:
    task = scoped_get(
        db, ProjectTask, task_id, user_id, PROJECT_SCOPE, project_id=project_id
    )
    authorize(db, user_id, Permission.task_delete, project_id)

    # Related comments are removed via FK ON DELETE CASCADE
    remove(db, task)