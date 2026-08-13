from fastapi import APIRouter, Depends
from sqlmodel import Session

from database import get_session
from deps import get_current_user
from models import User
from schemas.auth import MessageResponse
from schemas.task import (
    CreateTaskRequest,
    TaskResponse,
    UpdateTaskRequest,
)
from services.task_service import (
    create_task,
    delete_task,
    get_task,
    get_tasks_for_project,
    update_task,
)

router = APIRouter(prefix="/projects/{project_id}/tasks", tags=["tasks"])


def _to_response(task) -> TaskResponse:
    return TaskResponse(
        id=task.id,
        project_id=task.project_id,
        title=task.title,
        description=task.description,
        assigned_to=task.assigned_to,
        created_by=task.created_by,
        due_date=task.due_date,
        status=task.status,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


@router.post("", response_model=TaskResponse, status_code=201)
def create_task_endpoint(
    project_id: str,
    body: CreateTaskRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    task = create_task(
        {
            "project_id": project_id,
            "title": body.title,
            "description": body.description,
            "assigned_to": body.assigned_to,
            "due_date": body.due_date,
            "status": body.status,
            "created_by": current_user.id,
        },
        current_user.id,
        db,
    )
    return _to_response(task)


@router.get("", response_model=list[TaskResponse])
def list_tasks(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    return [_to_response(task) for task in get_tasks_for_project(project_id, current_user.id, db)]


@router.get("/{task_id}", response_model=TaskResponse)
def get_task_endpoint(
    project_id: str,
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    task = get_task(task_id, current_user.id, db)
    return _to_response(task)


@router.put("/{task_id}", response_model=TaskResponse)
def update_task_endpoint(
    project_id: str,
    task_id: str,
    body: UpdateTaskRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    task = update_task(task_id, current_user.id, body.model_dump(exclude_unset=True), db)
    return _to_response(task)


@router.delete("/{task_id}", response_model=MessageResponse)
def delete_task_endpoint(
    project_id: str,
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    delete_task(task_id, current_user.id, db)
    return MessageResponse(message="Task deleted successfully")
