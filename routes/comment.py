from fastapi import APIRouter, Depends
from sqlmodel import Session

from database import get_session
from deps import get_current_user
from models import User
from schemas.auth import MessageResponse
from schemas.comment import (
    CommentResponse,
    CreateCommentRequest,
    UpdateCommentRequest,
)
from services.comment_service import (
    create_comment,
    delete_comment,
    get_comments_for_task,
    update_comment,
)

router = APIRouter(prefix="/projects/{project_id}/tasks/{task_id}/comments", tags=["comments"])


def _to_response(comment) -> CommentResponse:
    return CommentResponse(
        id=comment.id,
        task_id=comment.task_id,
        user_id=comment.user_id,
        comment=comment.comment,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
    )


@router.post("", response_model=CommentResponse, status_code=201)
def create_comment_endpoint(
    project_id: str,
    task_id: str,
    body: CreateCommentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    comment = create_comment(
        {"task_id": task_id, "user_id": current_user.id, "comment": body.comment},
        current_user.id,
        db,
    )
    return _to_response(comment)


@router.get("", response_model=list[CommentResponse])
def list_comments(
    project_id: str,
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    return [_to_response(comment) for comment in get_comments_for_task(task_id, current_user.id, db)]


@router.put("/{comment_id}", response_model=CommentResponse)
def update_comment_endpoint(
    project_id: str,
    task_id: str,
    comment_id: str,
    body: UpdateCommentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    comment = update_comment(comment_id, current_user.id, body.model_dump(exclude_unset=True), db)
    return _to_response(comment)


@router.delete("/{comment_id}", response_model=MessageResponse)
def delete_comment_endpoint(
    project_id: str,
    task_id: str,
    comment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    delete_comment(comment_id, current_user.id, db)
    return MessageResponse(message="Comment deleted successfully")
