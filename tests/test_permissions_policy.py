from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlmodel import Session, select

from models import Project, ProjectMember, ProjectMemberRole, ProjectTask
from services.permissions import (
    ActorContext,
    Permission,
    authorize,
    can,
    pick_successor,
)


def _add_user(db: Session, email: str) -> str:
    from models import User

    user = User(email=email, hash_password="x")
    db.add(user)
    db.flush()
    return user.id


@pytest.fixture()
def project_world(db_session):
    """owner, admin, member, viewer users + project with all four membership rows."""
    owner = _add_user(db_session, "owner@x.com")
    admin = _add_user(db_session, "admin@x.com")
    member = _add_user(db_session, "member@x.com")
    viewer = _add_user(db_session, "viewer@x.com")
    stranger = _add_user(db_session, "stranger@x.com")

    project = Project(name="p", owner_id=owner)
    db_session.add(project)
    db_session.flush()

    for uid, role in (
        (owner, ProjectMemberRole.owner),
        (admin, ProjectMemberRole.admin),
        (member, ProjectMemberRole.member),
        (viewer, ProjectMemberRole.viewer),
    ):
        db_session.add(ProjectMember(project_id=project.id, user_id=uid, role=role))
    db_session.commit()
    return {
        "project_id": project.id,
        "owner": owner,
        "admin": admin,
        "member": member,
        "viewer": viewer,
        "stranger": stranger,
    }


def _member_row(db: Session, project_id: str, user_id: str) -> ProjectMember:
    return db.exec(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    ).one()


class TestAuthorizeHappyPath:
    @pytest.mark.parametrize(
        "permission,who",
        [
            (Permission.project_view, "viewer"),
            (Permission.task_create, "member"),
            (Permission.task_update, "admin"),
            (Permission.task_delete, "admin"),
            (Permission.comment_create, "member"),
            (Permission.member_add, "admin"),
            (Permission.member_role_update, "admin"),
            (Permission.member_remove, "admin"),
            (Permission.project_update, "admin"),
            (Permission.project_delete, "owner"),
            (Permission.project_transfer, "owner"),
        ],
    )
    def test_min_role_boundary_allows(self, db_session, project_world, permission, who):
        ctx = authorize(
            db_session, project_world[who], permission, project_world["project_id"]
        )
        assert isinstance(ctx, ActorContext)
        assert ctx.project.id == project_world["project_id"]

    @pytest.mark.parametrize(
        "permission,who,subject",
        [
            (Permission.comment_update, "admin", "viewer"),
            (Permission.comment_delete, "admin", "viewer"),
        ],
    )
    def test_author_rule_boundary_with_subject(self, db_session, project_world, permission, who, subject):
        ctx = authorize(
            db_session,
            project_world[who],
            permission,
            project_world["project_id"],
            subject_id=project_world[subject],
        )
        assert isinstance(ctx, ActorContext)

    @pytest.mark.parametrize(
        "permission,who",
        [
            (Permission.task_create, "viewer"),
            (Permission.task_update, "member"),
            (Permission.task_delete, "viewer"),
            (Permission.comment_create, "viewer"),
            (Permission.comment_update, "member"),
            (Permission.comment_delete, "viewer"),
            (Permission.member_add, "member"),
            (Permission.member_role_update, "member"),
            (Permission.member_remove, "viewer"),
            (Permission.project_update, "member"),
            (Permission.project_delete, "admin"),
            (Permission.project_transfer, "admin"),
        ],
    )
    def test_below_min_role_403(self, db_session, project_world, permission, who):
        with pytest.raises(HTTPException) as exc:
            authorize(
                db_session, project_world[who], permission, project_world["project_id"]
            )
        assert exc.value.status_code == 403
        assert exc.value.detail == "Insufficient permissions"

    def test_non_member_404_hides_project(self, db_session, project_world):
        with pytest.raises(HTTPException) as exc:
            authorize(
                db_session,
                project_world["stranger"],
                Permission.project_view,
                project_world["project_id"],
            )
        assert exc.value.status_code == 404
        assert exc.value.detail == "Project not found"

    def test_missing_project_404(self, db_session, project_world):
        with pytest.raises(HTTPException) as exc:
            authorize(
                db_session,
                project_world["owner"],
                Permission.project_view,
                "no-such-project",
            )
        assert exc.value.status_code == 404
        assert exc.value.detail == "Project not found"


class TestTaskCreateAssignee:
    def test_assignee_must_be_member(self, db_session, project_world):
        with pytest.raises(HTTPException) as exc:
            authorize(
                db_session,
                project_world["member"],
                Permission.task_create,
                project_world["project_id"],
                subject_id=project_world["stranger"],
            )
        assert exc.value.status_code == 404
        assert exc.value.detail == "User is not a project member"

    def test_assignee_member_allowed(self, db_session, project_world):
        authorize(
            db_session,
            project_world["member"],
            Permission.task_create,
            project_world["project_id"],
            subject_id=project_world["viewer"],
        )

    def test_no_assignee_allowed(self, db_session, project_world):
        authorize(
            db_session,
            project_world["member"],
            Permission.task_create,
            project_world["project_id"],
        )


class TestCommentAuthorBypass:
    def _make_comment(self, db_session, project_world, author_id) -> str:
        task = ProjectTask(
            project_id=project_world["project_id"],
            title="t",
            created_by=project_world["owner"],
        )
        db_session.add(task)
        db_session.flush()
        from models import ProjectTaskComment

        comment = ProjectTaskComment(task_id=task.id, user_id=author_id, comment="c")
        db_session.add(comment)
        db_session.flush()
        return comment.id, task.id

    def test_author_viewer_may_update(self, db_session, project_world):
        from models import ProjectTaskComment

        comment_id, _ = self._make_comment(
            db_session, project_world, project_world["viewer"]
        )
        comment = db_session.get(ProjectTaskComment, comment_id)
        ctx = authorize(
            db_session,
            project_world["viewer"],
            Permission.comment_update,
            project_world["project_id"],
            subject_id=comment.user_id,
        )
        assert ctx.project.id == project_world["project_id"]

    def test_author_not_a_member_may_delete(self, db_session, project_world):
        from models import ProjectTaskComment

        comment_id, _ = self._make_comment(
            db_session, project_world, project_world["stranger"]
        )
        comment = db_session.get(ProjectTaskComment, comment_id)
        ctx = authorize(
            db_session,
            project_world["stranger"],
            Permission.comment_delete,
            project_world["project_id"],
            subject_id=comment.user_id,
        )
        assert ctx.project.id == project_world["project_id"]

    def test_non_author_viewer_403(self, db_session, project_world):
        self._make_comment(db_session, project_world, project_world["viewer"])
        with pytest.raises(HTTPException) as exc:
            authorize(
                db_session,
                project_world["member"],
                Permission.comment_update,
                project_world["project_id"],
                subject_id=project_world["viewer"],
            )
        assert exc.value.status_code == 403


class TestMemberRules:
    def test_add_owner_role_forbidden(self, db_session, project_world):
        with pytest.raises(HTTPException) as exc:
            authorize(
                db_session,
                project_world["admin"],
                Permission.member_add,
                project_world["project_id"],
                subject_id=project_world["stranger"],
                role=ProjectMemberRole.owner,
            )
        assert exc.value.status_code == 400
        assert exc.value.detail == "Owner role can only be granted via project transfer"

    def test_role_update_missing_target_404(self, db_session, project_world):
        with pytest.raises(HTTPException) as exc:
            authorize(
                db_session,
                project_world["admin"],
                Permission.member_role_update,
                project_world["project_id"],
                subject_id=project_world["stranger"],
                role=ProjectMemberRole.member,
            )
        assert exc.value.status_code == 404
        assert exc.value.detail == "Project member not found"

    def test_role_update_target_owner_400(self, db_session, project_world):
        with pytest.raises(HTTPException) as exc:
            authorize(
                db_session,
                project_world["admin"],
                Permission.member_role_update,
                project_world["project_id"],
                subject_id=project_world["owner"],
                role=ProjectMemberRole.admin,
            )
        assert exc.value.status_code == 400
        assert exc.value.detail == "Owner role can only be changed via project transfer"

    def test_role_update_grant_owner_400(self, db_session, project_world):
        with pytest.raises(HTTPException) as exc:
            authorize(
                db_session,
                project_world["admin"],
                Permission.member_role_update,
                project_world["project_id"],
                subject_id=project_world["member"],
                role=ProjectMemberRole.owner,
            )
        assert exc.value.status_code == 400
        assert exc.value.detail == "Owner role can only be granted via project transfer"

    def test_remove_owner_400(self, db_session, project_world):
        with pytest.raises(HTTPException) as exc:
            authorize(
                db_session,
                project_world["admin"],
                Permission.member_remove,
                project_world["project_id"],
                subject_id=project_world["owner"],
            )
        assert exc.value.status_code == 400
        assert exc.value.detail == "Owner cannot be removed; transfer ownership first"

    def test_remove_returns_subject_row(self, db_session, project_world):
        ctx = authorize(
            db_session,
            project_world["admin"],
            Permission.member_remove,
            project_world["project_id"],
            subject_id=project_world["viewer"],
        )
        assert ctx.subject.user_id == project_world["viewer"]


class TestTransferRules:
    def test_self_transfer_400(self, db_session, project_world):
        with pytest.raises(HTTPException) as exc:
            authorize(
                db_session,
                project_world["owner"],
                Permission.project_transfer,
                project_world["project_id"],
                subject_id=project_world["owner"],
            )
        assert exc.value.status_code == 400
        assert exc.value.detail == "User is already the project owner"

    def test_missing_target_404(self, db_session, project_world):
        with pytest.raises(HTTPException) as exc:
            authorize(
                db_session,
                project_world["owner"],
                Permission.project_transfer,
                project_world["project_id"],
                subject_id=project_world["stranger"],
            )
        assert exc.value.status_code == 404
        assert exc.value.detail == "User is not a project member"


class TestCan:
    def test_true_for_allowed(self, db_session, project_world):
        assert can(
            db_session,
            project_world["viewer"],
            Permission.project_view,
            project_world["project_id"],
        )

    def test_false_for_denied(self, db_session, project_world):
        assert not can(
            db_session,
            project_world["viewer"],
            Permission.task_create,
            project_world["project_id"],
        )

    def test_false_for_non_member(self, db_session, project_world):
        assert not can(
            db_session,
            project_world["stranger"],
            Permission.project_view,
            project_world["project_id"],
        )


class TestPickSuccessor:
    def _member(self, user_id: str, role: ProjectMemberRole, joined_at: datetime):
        return ProjectMember(
            project_id="p", user_id=user_id, role=role, joined_at=joined_at
        )

    def test_highest_role_wins(self):
        now = datetime.now(timezone.utc)
        members = [
            self._member("v", ProjectMemberRole.viewer, now),
            self._member("m", ProjectMemberRole.member, now - timedelta(days=1)),
            self._member("a", ProjectMemberRole.admin, now - timedelta(days=2)),
        ]
        assert pick_successor(members).user_id == "a"

    def test_tie_breaks_to_earliest_joined(self):
        now = datetime.now(timezone.utc)
        members = [
            self._member("early", ProjectMemberRole.admin, now - timedelta(days=5)),
            self._member("late", ProjectMemberRole.admin, now - timedelta(days=1)),
        ]
        assert pick_successor(members).user_id == "early"

    def test_owner_excluded(self):
        now = datetime.now(timezone.utc)
        members = [
            self._member("owner", ProjectMemberRole.owner, now),
            self._member("m", ProjectMemberRole.member, now),
        ]
        assert pick_successor(members).user_id == "m"

    def test_empty_list_returns_none(self):
        assert pick_successor([]) is None

    def test_owner_only_returns_none(self):
        now = datetime.now(timezone.utc)
        assert pick_successor([self._member("owner", ProjectMemberRole.owner, now)]) is None