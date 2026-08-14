from fastapi import APIRouter, Depends
from sqlmodel import Session

from database import get_session
from deps import get_current_user
from models import ProjectTaskComment, User
from schemas.auth import MessageResponse
from schemas.comment import (
    CommentResponse,
    CreateCommentRequest,
    UpdateCommentRequest,
)
from services.comment_service import (
    create_comment,
    delete_comment,
    update_comment,
)
from services.scope import TASK_SCOPE, scoped_list

router = APIRouter(prefix="/projects/{project_id}/tasks/{task_id}/comments", tags=["comments"])


@router.post("", response_model=CommentResponse, status_code=201)
def create_comment_endpoint(
    project_id: str,
    task_id: str,
    body: CreateCommentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    comment = create_comment(project_id, task_id, body, current_user.id, db)
    return CommentResponse.model_validate(comment)


@router.get("", response_model=list[CommentResponse])
def list_comments(
    project_id: str,
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    comments = scoped_list(
        db,
        ProjectTaskComment,
        current_user.id,
        TASK_SCOPE,
        project_id=project_id,
        task_id=task_id,
    )
    return [CommentResponse.model_validate(comment) for comment in comments]


@router.put("/{comment_id}", response_model=CommentResponse)
def update_comment_endpoint(
    project_id: str,
    task_id: str,
    comment_id: str,
    body: UpdateCommentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    comment = update_comment(
        project_id, task_id, comment_id, body, current_user.id, db
    )
    return CommentResponse.model_validate(comment)


@router.delete("/{comment_id}", response_model=MessageResponse)
def delete_comment_endpoint(
    project_id: str,
    task_id: str,
    comment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    delete_comment(project_id, task_id, comment_id, current_user.id, db)
    return MessageResponse(message="Comment deleted successfully")