from fastapi import APIRouter, Depends
from sqlmodel import Session

from database import get_session
from deps import get_current_user
from models import ProjectTask, User
from schemas.auth import MessageResponse
from schemas.task import (
    CreateTaskRequest,
    TaskResponse,
    UpdateTaskRequest,
)
from services.scope import PROJECT_SCOPE, scoped_get, scoped_list
from services.task_service import (
    create_task,
    delete_task,
    update_task,
)

router = APIRouter(prefix="/projects/{project_id}/tasks", tags=["tasks"])


@router.post("", response_model=TaskResponse, status_code=201)
def create_task_endpoint(
    project_id: str,
    body: CreateTaskRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    task = create_task(project_id, body, current_user.id, db)
    return TaskResponse.model_validate(task)


@router.get("", response_model=list[TaskResponse])
def list_tasks(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    tasks = scoped_list(
        db, ProjectTask, current_user.id, PROJECT_SCOPE, project_id=project_id
    )
    return [TaskResponse.model_validate(task) for task in tasks]


@router.get("/{task_id}", response_model=TaskResponse)
def get_task_endpoint(
    project_id: str,
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    task = scoped_get(
        db,
        ProjectTask,
        task_id,
        current_user.id,
        PROJECT_SCOPE,
        project_id=project_id,
    )
    return TaskResponse.model_validate(task)


@router.put("/{task_id}", response_model=TaskResponse)
def update_task_endpoint(
    project_id: str,
    task_id: str,
    body: UpdateTaskRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    task = update_task(project_id, task_id, body, current_user.id, db)
    return TaskResponse.model_validate(task)


@router.delete("/{task_id}", response_model=MessageResponse)
def delete_task_endpoint(
    project_id: str,
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    delete_task(project_id, task_id, current_user.id, db)
    return MessageResponse(message="Task deleted successfully")