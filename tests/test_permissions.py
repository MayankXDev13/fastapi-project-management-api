"""
Authorization tests: project-scoped roles, 404 resource hiding, transfer,
owner immutability, and the adjacent bug fixes (task unassign, cascade deletes).
"""
import uuid
from datetime import datetime, timedelta, timezone

from sqlmodel import select


def _email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@test.com"


def _user(client, email: str, password: str = "pass123"):
    resp = client.post("/auth/register", json={"email": email, "password": password})
    assert resp.status_code == 201, resp.text
    tokens = client.post(
        "/auth/login", json={"email": email, "password": password}
    ).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    me = client.get("/auth/me", headers=headers).json()
    return {"id": me["id"], "headers": headers}


def _setup_project(client, member_count: int = 3):
    """Owner + [admin, member, viewer] members; returns dict keyed by role."""
    owner = _user(client, _email("owner"))
    resp = client.post("/projects", json={"name": "Auth Project"}, headers=owner["headers"])
    assert resp.status_code == 201, resp.text
    project_id = resp.json()["id"]

    roles = {}
    for role in ["admin", "member", "viewer"]:
        u = _user(client, _email(role))
        r = client.post(
            f"/projects/{project_id}/members",
            json={"user_id": u["id"], "role": role},
            headers=owner["headers"],
        )
        assert r.status_code == 201, r.text
        roles[role] = u
    roles["owner"] = owner
    return project_id, roles


def _create_task(client, project_id: str, headers: dict) -> str:
    resp = client.post(
        f"/projects/{project_id}/tasks",
        json={"project_id": project_id, "title": "Do the thing", "description": "desc"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Resource hiding: non-members get 404 on everything
# ---------------------------------------------------------------------------

class TestNonMember404:
    def test_non_member_cannot_read_project(self, client):
        pid, roles = _setup_project(client)
        outsider = _user(client, _email("outsider"))
        assert client.get(f"/projects/{pid}", headers=outsider["headers"]).status_code == 404

    def test_non_member_cannot_list_tasks(self, client):
        pid, roles = _setup_project(client)
        outsider = _user(client, _email("outsider"))
        resp = client.get(f"/projects/{pid}/tasks", headers=outsider["headers"])
        assert resp.status_code == 404

    def test_non_member_cannot_read_task(self, client):
        pid, roles = _setup_project(client)
        task_id = _create_task(client, pid, roles["owner"]["headers"])
        outsider = _user(client, _email("outsider"))
        resp = client.get(f"/projects/{pid}/tasks/{task_id}", headers=outsider["headers"])
        assert resp.status_code == 404

    def test_non_member_cannot_comment(self, client):
        pid, roles = _setup_project(client)
        task_id = _create_task(client, pid, roles["owner"]["headers"])
        outsider = _user(client, _email("outsider"))
        resp = client.post(
            f"/projects/{pid}/tasks/{task_id}/comments",
            json={"task_id": task_id, "comment": "hi"},
            headers=outsider["headers"],
        )
        assert resp.status_code == 404

    def test_non_member_cannot_list_members(self, client):
        pid, roles = _setup_project(client)
        outsider = _user(client, _email("outsider"))
        assert client.get(f"/projects/{pid}/members", headers=outsider["headers"]).status_code == 404


# ---------------------------------------------------------------------------
# Project endpoints
# ---------------------------------------------------------------------------

class TestProjectPermissions:
    def test_viewer_can_view(self, client):
        pid, roles = _setup_project(client)
        resp = client.get(f"/projects/{pid}", headers=roles["viewer"]["headers"])
        assert resp.status_code == 200

    def test_member_cannot_update_project(self, client):
        pid, roles = _setup_project(client)
        resp = client.put(
            f"/projects/{pid}", json={"name": "Hacked"}, headers=roles["member"]["headers"]
        )
        assert resp.status_code == 403

    def test_viewer_cannot_update_project(self, client):
        pid, roles = _setup_project(client)
        resp = client.put(
            f"/projects/{pid}", json={"name": "Hacked"}, headers=roles["viewer"]["headers"]
        )
        assert resp.status_code == 403

    def test_admin_can_update_project(self, client):
        pid, roles = _setup_project(client)
        resp = client.put(
            f"/projects/{pid}", json={"name": "Admin Renamed"}, headers=roles["admin"]["headers"]
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Admin Renamed"

    def test_admin_cannot_delete_project(self, client):
        pid, roles = _setup_project(client)
        resp = client.delete(f"/projects/{pid}", headers=roles["admin"]["headers"])
        assert resp.status_code == 403

    def test_owner_can_delete_project(self, client):
        pid, roles = _setup_project(client)
        resp = client.delete(f"/projects/{pid}", headers=roles["owner"]["headers"])
        assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Task endpoints
# ---------------------------------------------------------------------------

class TestTaskPermissions:
    def test_member_can_create_task(self, client):
        pid, roles = _setup_project(client)
        resp = client.post(
            f"/projects/{pid}/tasks",
            json={"project_id": pid, "title": "Member task"},
            headers=roles["member"]["headers"],
        )
        assert resp.status_code == 201

    def test_viewer_cannot_create_task(self, client):
        pid, roles = _setup_project(client)
        resp = client.post(
            f"/projects/{pid}/tasks",
            json={"project_id": pid, "title": "Viewer task"},
            headers=roles["viewer"]["headers"],
        )
        assert resp.status_code == 403

    def test_member_cannot_update_task(self, client):
        pid, roles = _setup_project(client)
        task_id = _create_task(client, pid, roles["owner"]["headers"])
        resp = client.put(
            f"/projects/{pid}/tasks/{task_id}",
            json={"project_id": pid, "title": "Hijacked"},
            headers=roles["member"]["headers"],
        )
        assert resp.status_code == 403

    def test_admin_can_update_task(self, client):
        pid, roles = _setup_project(client)
        task_id = _create_task(client, pid, roles["owner"]["headers"])
        resp = client.put(
            f"/projects/{pid}/tasks/{task_id}",
            json={"status": "in_progress"},
            headers=roles["admin"]["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "in_progress"

    def test_member_cannot_delete_task(self, client):
        pid, roles = _setup_project(client)
        task_id = _create_task(client, pid, roles["owner"]["headers"])
        resp = client.delete(f"/projects/{pid}/tasks/{task_id}", headers=roles["member"]["headers"])
        assert resp.status_code == 403

    def test_admin_can_delete_task(self, client):
        pid, roles = _setup_project(client)
        task_id = _create_task(client, pid, roles["owner"]["headers"])
        resp = client.delete(f"/projects/{pid}/tasks/{task_id}", headers=roles["admin"]["headers"])
        assert resp.status_code == 200

    def test_viewer_can_view_task(self, client):
        pid, roles = _setup_project(client)
        task_id = _create_task(client, pid, roles["owner"]["headers"])
        resp = client.get(f"/projects/{pid}/tasks/{task_id}", headers=roles["viewer"]["headers"])
        assert resp.status_code == 200


class TestTaskAssignment:
    def test_assign_to_member_succeeds(self, client):
        pid, roles = _setup_project(client)
        resp = client.post(
            f"/projects/{pid}/tasks",
            json={"project_id": pid, "title": "Assigned", "assigned_to": roles["member"]["id"]},
            headers=roles["owner"]["headers"],
        )
        assert resp.status_code == 201
        assert resp.json()["assigned_to"] == roles["member"]["id"]

    def test_assign_to_non_member_404(self, client):
        pid, roles = _setup_project(client)
        outsider = _user(client, _email("outsider"))
        resp = client.post(
            f"/projects/{pid}/tasks",
            json={"project_id": pid, "title": "Bad assign", "assigned_to": outsider["id"]},
            headers=roles["owner"]["headers"],
        )
        assert resp.status_code == 404

    def test_unassign_via_null(self, client):
        pid, roles = _setup_project(client)
        resp = client.post(
            f"/projects/{pid}/tasks",
            json={"project_id": pid, "title": "Assigned", "assigned_to": roles["member"]["id"]},
            headers=roles["owner"]["headers"],
        )
        task_id = resp.json()["id"]
        resp = client.put(
            f"/projects/{pid}/tasks/{task_id}",
            json={"assigned_to": None},
            headers=roles["owner"]["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["assigned_to"] is None

    def test_update_without_assigned_to_keeps_assignee(self, client):
        pid, roles = _setup_project(client)
        resp = client.post(
            f"/projects/{pid}/tasks",
            json={"project_id": pid, "title": "Assigned", "assigned_to": roles["member"]["id"]},
            headers=roles["owner"]["headers"],
        )
        task_id = resp.json()["id"]
        resp = client.put(
            f"/projects/{pid}/tasks/{task_id}",
            json={"project_id": pid, "title": "Renamed"},
            headers=roles["owner"]["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["assigned_to"] == roles["member"]["id"]


# ---------------------------------------------------------------------------
# Comment endpoints
# ---------------------------------------------------------------------------

class TestCommentPermissions:
    def test_viewer_cannot_comment(self, client):
        pid, roles = _setup_project(client)
        task_id = _create_task(client, pid, roles["owner"]["headers"])
        resp = client.post(
            f"/projects/{pid}/tasks/{task_id}/comments",
            json={"task_id": task_id, "comment": "hi"},
            headers=roles["viewer"]["headers"],
        )
        assert resp.status_code == 403

    def test_member_can_comment(self, client):
        pid, roles = _setup_project(client)
        task_id = _create_task(client, pid, roles["owner"]["headers"])
        resp = client.post(
            f"/projects/{pid}/tasks/{task_id}/comments",
            json={"task_id": task_id, "comment": "hi"},
            headers=roles["member"]["headers"],
        )
        assert resp.status_code == 201

    def test_viewer_can_read_comments(self, client):
        pid, roles = _setup_project(client)
        task_id = _create_task(client, pid, roles["owner"]["headers"])
        client.post(
            f"/projects/{pid}/tasks/{task_id}/comments",
            json={"task_id": task_id, "comment": "hi"},
            headers=roles["member"]["headers"],
        )
        resp = client.get(f"/projects/{pid}/tasks/{task_id}/comments", headers=roles["viewer"]["headers"])
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_member_cannot_delete_others_comment(self, client):
        pid, roles = _setup_project(client)
        task_id = _create_task(client, pid, roles["owner"]["headers"])
        comment_id = client.post(
            f"/projects/{pid}/tasks/{task_id}/comments",
            json={"task_id": task_id, "comment": "mine"},
            headers=roles["owner"]["headers"],
        ).json()["id"]
        resp = client.delete(
            f"/projects/{pid}/tasks/{task_id}/comments/{comment_id}",
            headers=roles["member"]["headers"],
        )
        assert resp.status_code == 403

    def test_author_can_delete_own_comment(self, client):
        pid, roles = _setup_project(client)
        task_id = _create_task(client, pid, roles["owner"]["headers"])
        comment_id = client.post(
            f"/projects/{pid}/tasks/{task_id}/comments",
            json={"task_id": task_id, "comment": "mine"},
            headers=roles["member"]["headers"],
        ).json()["id"]
        resp = client.delete(
            f"/projects/{pid}/tasks/{task_id}/comments/{comment_id}",
            headers=roles["member"]["headers"],
        )
        assert resp.status_code == 200

    def test_admin_can_delete_others_comment(self, client):
        pid, roles = _setup_project(client)
        task_id = _create_task(client, pid, roles["owner"]["headers"])
        comment_id = client.post(
            f"/projects/{pid}/tasks/{task_id}/comments",
            json={"task_id": task_id, "comment": "mine"},
            headers=roles["member"]["headers"],
        ).json()["id"]
        resp = client.delete(
            f"/projects/{pid}/tasks/{task_id}/comments/{comment_id}",
            headers=roles["admin"]["headers"],
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Member management
# ---------------------------------------------------------------------------

class TestMemberManagement:
    def test_member_cannot_add_member(self, client):
        pid, roles = _setup_project(client)
        newbie = _user(client, _email("newbie"))
        resp = client.post(
            f"/projects/{pid}/members",
            json={"user_id": newbie["id"], "role": "member"},
            headers=roles["member"]["headers"],
        )
        assert resp.status_code == 403

    def test_admin_can_add_member(self, client):
        pid, roles = _setup_project(client)
        newbie = _user(client, _email("newbie"))
        resp = client.post(
            f"/projects/{pid}/members",
            json={"user_id": newbie["id"], "role": "member"},
            headers=roles["admin"]["headers"],
        )
        assert resp.status_code == 201

    def test_member_cannot_change_role(self, client):
        pid, roles = _setup_project(client)
        resp = client.put(
            f"/projects/{pid}/members/{roles['viewer']['id']}",
            json={"new_role": "admin"},
            headers=roles["member"]["headers"],
        )
        assert resp.status_code == 403

    def test_admin_can_change_role(self, client):
        pid, roles = _setup_project(client)
        resp = client.put(
            f"/projects/{pid}/members/{roles['member']['id']}",
            json={"new_role": "admin"},
            headers=roles["admin"]["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "admin"

    def test_admin_cannot_remove_member(self, client):
        pid, roles = _setup_project(client)
        resp = client.delete(
            f"/projects/{pid}/members/{roles['member']['id']}",
            headers=roles["member"]["headers"],
        )
        assert resp.status_code == 403

    def test_admin_can_remove_member(self, client):
        pid, roles = _setup_project(client)
        resp = client.delete(
            f"/projects/{pid}/members/{roles['member']['id']}",
            headers=roles["admin"]["headers"],
        )
        assert resp.status_code == 200


class TestOwnerImmutability:
    def test_admin_cannot_change_owner_role(self, client):
        pid, roles = _setup_project(client)
        resp = client.put(
            f"/projects/{pid}/members/{roles['owner']['id']}",
            json={"new_role": "member"},
            headers=roles["admin"]["headers"],
        )
        assert resp.status_code == 400

    def test_admin_cannot_remove_owner(self, client):
        pid, roles = _setup_project(client)
        resp = client.delete(
            f"/projects/{pid}/members/{roles['owner']['id']}",
            headers=roles["admin"]["headers"],
        )
        assert resp.status_code == 400

    def test_cannot_add_owner_via_member_endpoint(self, client):
        pid, roles = _setup_project(client)
        newbie = _user(client, _email("newbie"))
        resp = client.post(
            f"/projects/{pid}/members",
            json={"user_id": newbie["id"], "role": "owner"},
            headers=roles["owner"]["headers"],
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Ownership transfer
# ---------------------------------------------------------------------------

class TestTransfer:
    def test_owner_transfers_to_admin(self, client):
        pid, roles = _setup_project(client)
        resp = client.post(
            f"/projects/{pid}/transfer",
            json={"user_id": roles["admin"]["id"]},
            headers=roles["owner"]["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["owner_id"] == roles["admin"]["id"]

    def test_transfer_updates_member_roles(self, client, db_session):
        from models import ProjectMember, ProjectMemberRole
        pid, roles = _setup_project(client)
        client.post(
            f"/projects/{pid}/transfer",
            json={"user_id": roles["admin"]["id"]},
            headers=roles["owner"]["headers"],
        )
        members = db_session.exec(
            select(ProjectMember).where(ProjectMember.project_id == pid)
        ).all()
        by_user = {m.user_id: m.role for m in members}
        assert by_user[roles["admin"]["id"]] == ProjectMemberRole.owner
        assert by_user[roles["owner"]["id"]] == ProjectMemberRole.member

    def test_new_owner_can_delete_project(self, client):
        pid, roles = _setup_project(client)
        client.post(
            f"/projects/{pid}/transfer",
            json={"user_id": roles["admin"]["id"]},
            headers=roles["owner"]["headers"],
        )
        assert client.delete(f"/projects/{pid}", headers=roles["admin"]["headers"]).status_code == 204

    def test_old_owner_cannot_delete_after_transfer(self, client):
        pid, roles = _setup_project(client)
        client.post(
            f"/projects/{pid}/transfer",
            json={"user_id": roles["admin"]["id"]},
            headers=roles["owner"]["headers"],
        )
        resp = client.delete(f"/projects/{pid}", headers=roles["owner"]["headers"])
        assert resp.status_code == 403

    def test_non_owner_cannot_transfer(self, client):
        pid, roles = _setup_project(client)
        resp = client.post(
            f"/projects/{pid}/transfer",
            json={"user_id": roles["member"]["id"]},
            headers=roles["admin"]["headers"],
        )
        assert resp.status_code == 403

    def test_transfer_to_non_member_404(self, client):
        pid, roles = _setup_project(client)
        outsider = _user(client, _email("outsider"))
        resp = client.post(
            f"/projects/{pid}/transfer",
            json={"user_id": outsider["id"]},
            headers=roles["owner"]["headers"],
        )
        assert resp.status_code == 404

    def test_transfer_to_self_400(self, client):
        pid, roles = _setup_project(client)
        resp = client.post(
            f"/projects/{pid}/transfer",
            json={"user_id": roles["owner"]["id"]},
            headers=roles["owner"]["headers"],
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Cascade deletes (bug fix: FK ON DELETE CASCADE replaces hand-rolled deletes)
# ---------------------------------------------------------------------------

class TestCascadeDeletes:
    def test_delete_project_removes_members_tasks_comments(self, client, db_session):
        from models import ProjectMember, ProjectTask, ProjectTaskComment
        pid, roles = _setup_project(client)
        task_id = _create_task(client, pid, roles["owner"]["headers"])
        client.post(
            f"/projects/{pid}/tasks/{task_id}/comments",
            json={"task_id": task_id, "comment": "bye"},
            headers=roles["member"]["headers"],
        )
        assert client.delete(f"/projects/{pid}", headers=roles["owner"]["headers"]).status_code == 204
        assert db_session.exec(select(ProjectMember).where(ProjectMember.project_id == pid)).all() == []
        assert db_session.exec(select(ProjectTask).where(ProjectTask.project_id == pid)).all() == []
        assert db_session.exec(
            select(ProjectTaskComment).where(ProjectTaskComment.task_id == task_id)
        ).all() == []

    def test_delete_task_removes_comments(self, client, db_session):
        from models import ProjectTaskComment
        pid, roles = _setup_project(client)
        task_id = _create_task(client, pid, roles["owner"]["headers"])
        client.post(
            f"/projects/{pid}/tasks/{task_id}/comments",
            json={"task_id": task_id, "comment": "bye"},
            headers=roles["member"]["headers"],
        )
        assert client.delete(
            f"/projects/{pid}/tasks/{task_id}", headers=roles["owner"]["headers"]
        ).status_code == 200
        assert db_session.exec(
            select(ProjectTaskComment).where(ProjectTaskComment.task_id == task_id)
        ).all() == []


class TestRemoveMemberUnassignsTasks:
    def test_removed_member_loses_assignments(self, client, db_session):
        from models import ProjectTask
        pid, roles = _setup_project(client)
        resp = client.post(
            f"/projects/{pid}/tasks",
            json={"project_id": pid, "title": "Assigned", "assigned_to": roles["member"]["id"]},
            headers=roles["owner"]["headers"],
        )
        task_id = resp.json()["id"]
        assert client.delete(
            f"/projects/{pid}/members/{roles['member']['id']}",
            headers=roles["owner"]["headers"],
        ).status_code == 200
        task = db_session.get(ProjectTask, task_id)
        assert task.assigned_to is None


# ---------------------------------------------------------------------------
# delete_user_cascade helper (unit tests)
# ---------------------------------------------------------------------------

class TestDeleteUserCascade:
    def _user_row(self, db_session, email):
        from models import User
        from utils.auth import hash_password
        user = User(email=email, hash_password=hash_password("pass123"))
        db_session.add(user)
        db_session.flush()
        return user

    def test_ownership_transfers_to_highest_role(self, db_session):
        from models import Project, ProjectMember, ProjectMemberRole, User
        from services.project_service import create_project
        from services.user_service import delete_user_cascade

        owner = self._user_row(db_session, _email("owner"))
        admin = self._user_row(db_session, _email("admin"))
        member = self._user_row(db_session, _email("member"))
        project = create_project("P", None, owner.id, db_session)
        db_session.add(ProjectMember(project_id=project.id, user_id=admin.id, role=ProjectMemberRole.admin))
        db_session.add(ProjectMember(project_id=project.id, user_id=member.id, role=ProjectMemberRole.member))
        db_session.commit()

        delete_user_cascade(owner.id, db_session)

        assert db_session.get(User, owner.id) is None
        assert db_session.get(Project, project.id).owner_id == admin.id

    def test_tie_breaks_to_earliest_joined(self, db_session):
        from models import Project, ProjectMember, ProjectMemberRole, User
        from services.project_service import create_project
        from services.user_service import delete_user_cascade

        owner = self._user_row(db_session, _email("owner"))
        early = self._user_row(db_session, _email("early"))
        late = self._user_row(db_session, _email("late"))
        project = create_project("P", None, owner.id, db_session)
        late_m = ProjectMember(project_id=project.id, user_id=late.id, role=ProjectMemberRole.member)
        early_m = ProjectMember(project_id=project.id, user_id=early.id, role=ProjectMemberRole.member)
        early_m.joined_at = datetime.now(timezone.utc) - timedelta(days=5)
        db_session.add(early_m)
        db_session.add(late_m)
        db_session.commit()

        delete_user_cascade(owner.id, db_session)

        assert db_session.get(Project, project.id).owner_id == early.id

    def test_ownerless_project_is_deleted(self, db_session):
        from models import Project, User
        from services.project_service import create_project
        from services.user_service import delete_user_cascade

        owner = self._user_row(db_session, _email("owner"))
        project = create_project("P", None, owner.id, db_session)

        delete_user_cascade(owner.id, db_session)

        assert db_session.get(Project, project.id) is None
        assert db_session.get(User, owner.id) is None

    def test_user_without_projects_is_deleted(self, db_session):
        from models import User
        from services.user_service import delete_user_cascade

        user = self._user_row(db_session, _email("nobody"))
        delete_user_cascade(user.id, db_session)
        assert db_session.get(User, user.id) is None

    def test_unknown_user_is_noop(self, db_session):
        from services.user_service import delete_user_cascade
        delete_user_cascade("does-not-exist", db_session)
