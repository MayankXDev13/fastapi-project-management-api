from fastapi import HTTPException, status
from sqlmodel import Session, select, update

from models import ProjectMember, ProjectMemberRole, ProjectTask
from persistence import remove, save
from services.permissions import Permission, authorize
from services.scope import PROJECT_SCOPE, scoped_list


def get_project_members(
    project_id: str, user_id: str, db: Session
) -> list[ProjectMember]:
    return scoped_list(
        db, ProjectMember, user_id, PROJECT_SCOPE, project_id=project_id
    )


def add_member_to_project(
    project_id: str,
    user_id: str,
    actor_id: str,
    db: Session,
    role: ProjectMemberRole = ProjectMemberRole.member,
) -> ProjectMember:
    authorize(
        db,
        actor_id,
        Permission.member_add,
        project_id,
        subject_id=user_id,
        role=role,
    )

    existing = db.exec(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a project member",
        )

    return save(db, ProjectMember(project_id=project_id, user_id=user_id, role=role))


def update_member_role(
    project_id: str,
    target_user_id: str,
    actor_id: str,
    new_role: ProjectMemberRole | str,
    db: Session,
) -> ProjectMember:
    ctx = authorize(
        db,
        actor_id,
        Permission.member_role_update,
        project_id,
        subject_id=target_user_id,
        role=new_role,
    )

    ctx.subject.role = ProjectMemberRole(new_role) if isinstance(new_role, str) else new_role
    return save(db, ctx.subject)


def remove_member_from_project(
    project_id: str, target_user_id: str, actor_id: str, db: Session
) -> None:
    ctx = authorize(
        db,
        actor_id,
        Permission.member_remove,
        project_id,
        subject_id=target_user_id,
    )

    db.exec(
        update(ProjectTask)
        .where(
            ProjectTask.project_id == project_id,
            ProjectTask.assigned_to == target_user_id,
        )
        .values(assigned_to=None)
    )
    remove(db, ctx.subject)