from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from database import get_session
from deps import get_current_user
from models import User
from schemas.base import Page
from schemas.project import (
    CreateProjectRequest,
    ProjectResponse,
    TransferProjectRequest,
    UpdateProjectRequest,
)
from services.project_service import (
    create_project,
    delete_project,
    get_all_projects,
    get_project,
    transfer_project,
    update_project,
)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=201)
def create_project_endpoint(
    body: CreateProjectRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    project = create_project(body.name, body.description, current_user.id, db)
    return ProjectResponse.model_validate(project)


@router.get("", response_model=Page[ProjectResponse])
def list_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    search: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    result = get_all_projects(
        db=db,
        user_id=current_user.id,
        page=page,
        page_size=page_size,
        search=search,
    )
    return Page[ProjectResponse].model_validate(result)


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project_endpoint(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    project = get_project(project_id, current_user.id, db)
    return ProjectResponse.model_validate(project)


@router.put("/{project_id}", response_model=ProjectResponse)
def update_project_endpoint(
    project_id: str,
    body: UpdateProjectRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    project = update_project(
        project_id, current_user.id, body.model_dump(exclude_unset=True), db
    )
    return ProjectResponse.model_validate(project)


@router.delete("/{project_id}", status_code=204)
def delete_project_endpoint(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    delete_project(project_id, current_user.id, db)


@router.post("/{project_id}/transfer", response_model=ProjectResponse)
def transfer_project_endpoint(
    project_id: str,
    body: TransferProjectRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    project = transfer_project(project_id, body.user_id, current_user.id, db)
    return ProjectResponse.model_validate(project)