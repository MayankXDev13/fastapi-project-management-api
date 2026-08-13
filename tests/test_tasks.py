"""
Tests for /projects/{project_id}/tasks routes
"""
import pytest


def _auth_and_project(client):
    from tests.conftest import auth_headers, create_project
    auth = auth_headers(client)
    h = auth["headers"]
    proj = create_project(client, h)
    return h, proj["id"]


class TestTaskCreate:
    def test_create_task_success(self, client):
        h, pid = _auth_and_project(client)
        resp = client.post(f"/projects/{pid}/tasks", json={"project_id": pid, "title": "Task 1", "description": "do it"}, headers=h)
        assert resp.status_code == 201
        body = resp.json()
        assert body["title"] == "Task 1"
        assert body["project_id"] == pid
        assert body["status"] == "todo"
        assert "id" in body
        assert "created_by" in body

    def test_create_task_with_status_and_assignee(self, client):
        h, pid = _auth_and_project(client)
        # need a user to assign to — use own user via /auth/me
        me = client.get("/auth/me", headers=h).json()
        resp = client.post(
            f"/projects/{pid}/tasks",
            json={"project_id": pid, "title": "Assigned", "assigned_to": me["id"], "status": "in_progress"},
            headers=h,
        )
        assert resp.status_code == 201
        assert resp.json()["assigned_to"] == me["id"]
        assert resp.json()["status"] == "in_progress"

    def test_create_task_requires_auth_401(self, client):
        resp = client.post("/projects/pid/tasks", json={"title": "X"})
        assert resp.status_code == 401

    def test_create_task_missing_title_422(self, client):
        h, pid = _auth_and_project(client)
        resp = client.post(f"/projects/{pid}/tasks", json={"project_id": pid}, headers=h)
        assert resp.status_code == 422


class TestTaskListGet:
    def test_list_tasks_empty(self, client):
        h, pid = _auth_and_project(client)
        resp = client.get(f"/projects/{pid}/tasks", headers=h)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_tasks_returns_created(self, client):
        h, pid = _auth_and_project(client)
        client.post(f"/projects/{pid}/tasks", json={"project_id": pid, "title": "T1"}, headers=h)
        client.post(f"/projects/{pid}/tasks", json={"project_id": pid, "title": "T2"}, headers=h)
        resp = client.get(f"/projects/{pid}/tasks", headers=h)
        assert len(resp.json()) == 2

    def test_get_task_success(self, client):
        h, pid = _auth_and_project(client)
        created = client.post(f"/projects/{pid}/tasks", json={"project_id": pid, "title": "GetMe"}, headers=h).json()
        resp = client.get(f"/projects/{pid}/tasks/{created['id']}", headers=h)
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    def test_get_task_not_found_404(self, client):
        h, pid = _auth_and_project(client)
        resp = client.get(f"/projects/{pid}/tasks/does-not-exist", headers=h)
        assert resp.status_code == 404

    def test_list_tasks_requires_auth(self, client):
        resp = client.get("/projects/pid/tasks")
        assert resp.status_code == 401


class TestTaskUpdateDelete:
    def test_update_task_success(self, client):
        h, pid = _auth_and_project(client)
        created = client.post(f"/projects/{pid}/tasks", json={"project_id": pid, "title": "Orig"}, headers=h).json()
        resp = client.put(f"/projects/{pid}/tasks/{created['id']}", json={"title": "Updated", "status": "completed"}, headers=h)
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated"
        assert resp.json()["status"] == "completed"

    def test_update_task_not_found_404(self, client):
        h, pid = _auth_and_project(client)
        resp = client.put(f"/projects/{pid}/tasks/nope", json={"title": "X"}, headers=h)
        assert resp.status_code == 404

    def test_update_task_partial_keeps_other_fields(self, client):
        h, pid = _auth_and_project(client)
        created = client.post(f"/projects/{pid}/tasks", json={"project_id": pid, "title": "Keep", "description": "desc"}, headers=h).json()
        resp = client.put(f"/projects/{pid}/tasks/{created['id']}", json={"status": "review"}, headers=h)
        assert resp.json()["title"] == "Keep"
        assert resp.json()["status"] == "review"

    def test_delete_task_success(self, client):
        h, pid = _auth_and_project(client)
        created = client.post(f"/projects/{pid}/tasks", json={"project_id": pid, "title": "Del"}, headers=h).json()
        resp = client.delete(f"/projects/{pid}/tasks/{created['id']}", headers=h)
        assert resp.status_code == 200
        assert "deleted" in resp.json()["message"].lower()
        # get should now 404
        resp2 = client.get(f"/projects/{pid}/tasks/{created['id']}", headers=h)
        assert resp2.status_code == 404

    def test_delete_task_not_found_404(self, client):
        h, pid = _auth_and_project(client)
        resp = client.delete(f"/projects/{pid}/tasks/nope", headers=h)
        assert resp.status_code == 404

    def test_update_delete_require_auth(self, client):
        resp = client.put("/projects/p/t/tasks/tid", json={"title": "X"})
        assert resp.status_code == 401
        resp = client.delete("/projects/p/t/tasks/tid")
        assert resp.status_code == 401
