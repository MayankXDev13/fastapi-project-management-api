"""Unit tests for scoped_get / scoped_list — the URL is the authority."""
import pytest
from fastapi import HTTPException
from sqlmodel import Session

from models import (
    Project,
    ProjectMember,
    ProjectMemberRole,
    ProjectTask,
    ProjectTaskComment,
    User,
)
from services.scope import PROJECT_SCOPE, TASK_SCOPE, scoped_get, scoped_list


@pytest.fixture()
def world(db_session):
    """Two projects (A, B), one member each (alice in A, bob in B)."""
    alice = User(email="alice@x.com", hash_password="x")
    bob = User(email="bob@x.com", hash_password="x")
    db_session.add_all([alice, bob])
    db_session.flush()

    pa = Project(name="A", owner_id=alice.id)
    pb = Project(name="B", owner_id=bob.id)
    db_session.add_all([pa, pb])
    db_session.flush()

    db_session.add_all(
        [
            ProjectMember(project_id=pa.id, user_id=alice.id, role=ProjectMemberRole.owner),
            ProjectMember(project_id=pb.id, user_id=bob.id, role=ProjectMemberRole.owner),
        ]
    )
    db_session.flush()

    task_a = ProjectTask(project_id=pa.id, title="ta", created_by=alice.id)
    task_b = ProjectTask(project_id=pb.id, title="tb", created_by=bob.id)
    db_session.add_all([task_a, task_b])
    db_session.flush()

    comment_a = ProjectTaskComment(task_id=task_a.id, user_id=alice.id, comment="ca")
    comment_b = ProjectTaskComment(task_id=task_b.id, user_id=bob.id, comment="cb")
    db_session.add_all([comment_a, comment_b])
    db_session.commit()

    return {
        "alice": alice.id,
        "bob": bob.id,
        "pa": pa.id,
        "pb": pb.id,
        "task_a": task_a.id,
        "task_b": task_b.id,
        "comment_a": comment_a.id,
        "comment_b": comment_b.id,
    }


class TestScopedGetProjectScope:
    def test_member_fetches_task(self, db_session, world):
        task = scoped_get(
            db_session,
            ProjectTask,
            world["task_a"],
            world["alice"],
            PROJECT_SCOPE,
            project_id=world["pa"],
        )
        assert task.id == world["task_a"]

    def test_missing_task_404_task_not_found(self, db_session, world):
        with pytest.raises(HTTPException) as exc:
            scoped_get(
                db_session,
                ProjectTask,
                "missing",
                world["alice"],
                PROJECT_SCOPE,
                project_id=world["pa"],
            )
        assert exc.value.status_code == 404
        assert exc.value.detail == "Task not found"

    def test_url_lie_task_from_other_project_404(self, db_session, world):
        # task_b is not under project pa — the URL lies
        with pytest.raises(HTTPException) as exc:
            scoped_get(
                db_session,
                ProjectTask,
                world["task_b"],
                world["alice"],
                PROJECT_SCOPE,
                project_id=world["pa"],
            )
        assert exc.value.status_code == 404

    def test_non_member_404_project_not_found(self, db_session, world):
        with pytest.raises(HTTPException) as exc:
            scoped_get(
                db_session,
                ProjectTask,
                world["task_a"],
                world["bob"],
                PROJECT_SCOPE,
                project_id=world["pa"],
            )
        assert exc.value.status_code == 404
        assert exc.value.detail == "Project not found"

    def test_non_member_missing_task_hides_project(self, db_session, world):
        # non-member querying a missing task → Project not found, not Task not found
        with pytest.raises(HTTPException) as exc:
            scoped_get(
                db_session,
                ProjectTask,
                "missing",
                world["bob"],
                PROJECT_SCOPE,
                project_id=world["pa"],
            )
        assert exc.value.status_code == 404
        assert exc.value.detail == "Project not found"


class TestScopedGetTaskScope:
    def test_member_fetches_comment(self, db_session, world):
        comment = scoped_get(
            db_session,
            ProjectTaskComment,
            world["comment_a"],
            world["alice"],
            TASK_SCOPE,
            project_id=world["pa"],
            task_id=world["task_a"],
        )
        assert comment.id == world["comment_a"]

    def test_url_lie_comment_under_wrong_task_404(self, db_session, world):
        # comment_a belongs to task_a; URL claims task_b
        with pytest.raises(HTTPException) as exc:
            scoped_get(
                db_session,
                ProjectTaskComment,
                world["comment_a"],
                world["alice"],
                TASK_SCOPE,
                project_id=world["pa"],
                task_id=world["task_b"],
            )
        assert exc.value.status_code == 404

    def test_url_lie_task_under_wrong_project_404(self, db_session, world):
        # comment_a under task_a, but URL project is B (alice is not in B)
        with pytest.raises(HTTPException) as exc:
            scoped_get(
                db_session,
                ProjectTaskComment,
                world["comment_a"],
                world["alice"],
                TASK_SCOPE,
                project_id=world["pb"],
                task_id=world["task_a"],
            )
        assert exc.value.status_code == 404

    def test_missing_comment_404_comment_not_found(self, db_session, world):
        with pytest.raises(HTTPException) as exc:
            scoped_get(
                db_session,
                ProjectTaskComment,
                "missing",
                world["alice"],
                TASK_SCOPE,
                project_id=world["pa"],
                task_id=world["task_a"],
            )
        assert exc.value.status_code == 404
        assert exc.value.detail == "Comment not found"


class TestScopedListProjectScope:
    def test_lists_only_projects_tasks(self, db_session, world):
        tasks = scoped_list(
            db_session, ProjectTask, world["alice"], PROJECT_SCOPE, project_id=world["pa"]
        )
        assert [t.id for t in tasks] == [world["task_a"]]

    def test_members_list(self, db_session, world):
        members = scoped_list(
            db_session,
            ProjectMember,
            world["alice"],
            PROJECT_SCOPE,
            project_id=world["pa"],
        )
        assert [m.user_id for m in members] == [world["alice"]]

    def test_non_member_404(self, db_session, world):
        with pytest.raises(HTTPException) as exc:
            scoped_list(
                db_session, ProjectTask, world["bob"], PROJECT_SCOPE, project_id=world["pa"]
            )
        assert exc.value.status_code == 404
        assert exc.value.detail == "Project not found"


class TestScopedListTaskScope:
    def test_lists_comments_of_task(self, db_session, world):
        comments = scoped_list(
            db_session,
            ProjectTaskComment,
            world["alice"],
            TASK_SCOPE,
            project_id=world["pa"],
            task_id=world["task_a"],
        )
        assert [c.id for c in comments] == [world["comment_a"]]

    def test_missing_task_404(self, db_session, world):
        with pytest.raises(HTTPException) as exc:
            scoped_list(
                db_session,
                ProjectTaskComment,
                world["alice"],
                TASK_SCOPE,
                project_id=world["pa"],
                task_id="missing",
            )
        assert exc.value.status_code == 404
        assert exc.value.detail == "Task not found"

    def test_task_under_foreign_project_404(self, db_session, world):
        with pytest.raises(HTTPException) as exc:
            scoped_list(
                db_session,
                ProjectTaskComment,
                world["bob"],
                TASK_SCOPE,
                project_id=world["pb"],
                task_id=world["task_a"],
            )
        assert exc.value.status_code == 404

    def test_missing_task_id_raises_value_error(self, db_session, world):
        with pytest.raises(ValueError):
            scoped_list(
                db_session,
                ProjectTaskComment,
                world["alice"],
                TASK_SCOPE,
                project_id=world["pa"],
            )


class TestScopedListExtras:
    def test_limit_and_offset(self, db_session, world):
        tasks = scoped_list(
            db_session,
            ProjectTask,
            world["alice"],
            PROJECT_SCOPE,
            project_id=world["pa"],
            limit=1,
            offset=0,
        )
        assert len(tasks) == 1