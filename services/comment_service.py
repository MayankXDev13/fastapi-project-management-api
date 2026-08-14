from sqlmodel import Session

from models import ProjectTask, ProjectTaskComment
from persistence import remove, save
from schemas.base import build_entity
from schemas.comment import CreateCommentRequest, UpdateCommentRequest
from services.permissions import Permission, authorize
from services.scope import PROJECT_SCOPE, TASK_SCOPE, scoped_get


def create_comment(
    project_id: str,
    task_id: str,
    body: CreateCommentRequest,
    user_id: str,
    db: Session,
) -> ProjectTaskComment:
    task = scoped_get(
        db, ProjectTask, task_id, user_id, PROJECT_SCOPE, project_id=project_id
    )
    authorize(db, user_id, Permission.comment_create, project_id)

    return save(
        db,
        build_entity(
            ProjectTaskComment,
            body,
            task_id=task.id,
            user_id=user_id,
        ),
    )


def update_comment(
    project_id: str,
    task_id: str,
    comment_id: str,
    body: UpdateCommentRequest,
    user_id: str,
    db: Session,
) -> ProjectTaskComment:
    comment = scoped_get(
        db,
        ProjectTaskComment,
        comment_id,
        user_id,
        TASK_SCOPE,
        project_id=project_id,
        task_id=task_id,
    )
    authorize(
        db,
        user_id,
        Permission.comment_update,
        project_id,
        subject_id=comment.user_id,
    )

    if body.comment is not None:
        comment.comment = body.comment

    return save(db, comment)


def delete_comment(
    project_id: str,
    task_id: str,
    comment_id: str,
    user_id: str,
    db: Session,
) -> None:
    comment = scoped_get(
        db,
        ProjectTaskComment,
        comment_id,
        user_id,
        TASK_SCOPE,
        project_id=project_id,
        task_id=task_id,
    )
    authorize(
        db,
        user_id,
        Permission.comment_delete,
        project_id,
        subject_id=comment.user_id,
    )
    remove(db, comment)