from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlmodel import Session, select

from models import ProjectMemberRole, ProjectTask, ProjectTaskComment
from services.permissions import get_membership_or_404, require_role

OWNER_OR_ADMIN = {ProjectMemberRole.owner, ProjectMemberRole.admin}
NON_VIEWER = {ProjectMemberRole.owner, ProjectMemberRole.admin, ProjectMemberRole.member}


def _can_manage_comment(
    comment: ProjectTaskComment, user_id: str, db: Session
) -> None:
    if comment.user_id == user_id:
        return
    require_role(db, comment.task.project_id, user_id, OWNER_OR_ADMIN)


def create_comment(
    comment_data: dict[str, Any], user_id: str, db: Session
) -> ProjectTaskComment:
    task = db.get(ProjectTask, comment_data["task_id"])
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    require_role(db, task.project_id, user_id, NON_VIEWER)

    comment = ProjectTaskComment(**comment_data)
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


def get_comments_for_task(
    task_id: str, user_id: str, db: Session
) -> list[ProjectTaskComment]:
    task = db.get(ProjectTask, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    get_membership_or_404(db, task.project_id, user_id)
    return db.exec(
        select(ProjectTaskComment).where(ProjectTaskComment.task_id == task_id)
    ).all()


def update_comment(
    comment_id: str, user_id: str, updated_data: dict[str, Any], db: Session
) -> ProjectTaskComment:
    comment = db.get(ProjectTaskComment, comment_id)
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found",
        )
    _can_manage_comment(comment, user_id, db)

    if "comment" in updated_data and updated_data["comment"] is not None:
        comment.comment = updated_data["comment"]

    comment.updated_at = datetime.now(timezone.utc)
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


def delete_comment(comment_id: str, user_id: str, db: Session) -> None:
    comment = db.get(ProjectTaskComment, comment_id)
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found",
        )
    _can_manage_comment(comment, user_id, db)
    db.delete(comment)
    db.commit()