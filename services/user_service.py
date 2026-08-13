from sqlmodel import Session, select

from models import Project, ProjectMember, ProjectMemberRole, User

_ROLE_RANK = {
    ProjectMemberRole.admin: 2,
    ProjectMemberRole.member: 1,
    ProjectMemberRole.viewer: 0,
}


def _pick_successor(members: list[ProjectMember]) -> ProjectMember | None:
    candidates = [m for m in members if m.role != ProjectMemberRole.owner]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda m: (_ROLE_RANK[m.role], -m.joined_at.timestamp()),
    )


def delete_user_cascade(user_id: str, db: Session) -> None:
    user = db.get(User, user_id)
    if not user:
        return

    owned_projects = db.exec(
        select(Project).where(Project.owner_id == user_id)
    ).all()

    for project in owned_projects:
        members = db.exec(
            select(ProjectMember).where(ProjectMember.project_id == project.id)
        ).all()
        successor = _pick_successor(members)
        if successor:
            project.owner_id = successor.user_id
            successor.role = ProjectMemberRole.owner
            db.add(project)
            db.add(successor)
        else:
            db.delete(project)

    db.delete(user)
    db.commit()