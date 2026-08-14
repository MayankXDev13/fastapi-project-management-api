from sqlmodel import Session, select

from models import Project, ProjectMember, ProjectMemberRole, User
from persistence import transaction
from services.permissions import pick_successor


def delete_user_cascade(user_id: str, db: Session) -> None:
    user = db.get(User, user_id)
    if not user:
        return

    with transaction(db):
        owned_projects = db.exec(
            select(Project).where(Project.owner_id == user_id)
        ).all()

        for project in owned_projects:
            members = db.exec(
                select(ProjectMember).where(ProjectMember.project_id == project.id)
            ).all()
            successor = pick_successor(members)
            if successor:
                project.owner_id = successor.user_id
                successor.role = ProjectMemberRole.owner
                db.add(project)
                db.add(successor)
            else:
                db.delete(project)

        db.delete(user)