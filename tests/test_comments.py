"""
Tests for /projects/{project_id}/tasks/{task_id}/comments
"""
import pytest


def _setup_project_task(client):
    from tests.conftest import auth_headers, create_project
    auth = auth_headers(client)
    h = auth["headers"]
    proj = create_project(client, h)
    task = client.post(f"/projects/{proj['id']}/tasks", json={"project_id": proj["id"], "title": "T"}, headers=h).json()
    return h, proj["id"], task["id"]


class TestCommentCreate:
    def test_create_comment_success(self, client):
        h, pid, tid = _setup_project_task(client)
        resp = client.post(f"/projects/{pid}/tasks/{tid}/comments", json={"task_id": tid, "comment": "Nice work!"}, headers=h)
        assert resp.status_code == 201
        body = resp.json()
        assert body["comment"] == "Nice work!"
        assert body["task_id"] == tid
        assert "id" in body
        assert "user_id" in body

    def test_create_comment_requires_auth(self, client):
        resp = client.post("/projects/p/tasks/t/comments", json={"task_id": "t", "comment": "hi"})
        assert resp.status_code == 401

    def test_create_comment_missing_field_422(self, client):
        h, pid, tid = _setup_project_task(client)
        resp = client.post(f"/projects/{pid}/tasks/{tid}/comments", json={"task_id": tid}, headers=h)
        assert resp.status_code == 422


class TestCommentList:
    def test_list_comments_empty(self, client):
        h, pid, tid = _setup_project_task(client)
        resp = client.get(f"/projects/{pid}/tasks/{tid}/comments", headers=h)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_comments_returns_all(self, client):
        h, pid, tid = _setup_project_task(client)
        client.post(f"/projects/{pid}/tasks/{tid}/comments", json={"task_id": tid, "comment": "c1"}, headers=h)
        client.post(f"/projects/{pid}/tasks/{tid}/comments", json={"task_id": tid, "comment": "c2"}, headers=h)
        resp = client.get(f"/projects/{pid}/tasks/{tid}/comments", headers=h)
        assert len(resp.json()) == 2

    def test_list_requires_auth(self, client):
        resp = client.get("/projects/p/tasks/t/comments")
        assert resp.status_code == 401


class TestCommentUpdateDelete:
    def test_update_comment_success(self, client):
        h, pid, tid = _setup_project_task(client)
        created = client.post(f"/projects/{pid}/tasks/{tid}/comments", json={"task_id": tid, "comment": "orig"}, headers=h).json()
        resp = client.put(f"/projects/{pid}/tasks/{tid}/comments/{created['id']}", json={"comment": "updated"}, headers=h)
        assert resp.status_code == 200
        assert resp.json()["comment"] == "updated"

    def test_update_comment_not_found_404(self, client):
        h, pid, tid = _setup_project_task(client)
        resp = client.put(f"/projects/{pid}/tasks/{tid}/comments/nope", json={"comment": "x"}, headers=h)
        assert resp.status_code == 404

    def test_delete_comment_success(self, client):
        h, pid, tid = _setup_project_task(client)
        created = client.post(f"/projects/{pid}/tasks/{tid}/comments", json={"task_id": tid, "comment": "del"}, headers=h).json()
        resp = client.delete(f"/projects/{pid}/tasks/{tid}/comments/{created['id']}", headers=h)
        assert resp.status_code == 200
        assert "deleted" in resp.json()["message"].lower()

    def test_delete_comment_not_found_404(self, client):
        h, pid, tid = _setup_project_task(client)
        resp = client.delete(f"/projects/{pid}/tasks/{tid}/comments/nope", headers=h)
        assert resp.status_code == 404

    def test_update_delete_require_auth(self, client):
        resp = client.put("/projects/p/tasks/t/comments/c", json={"comment": "x"})
        assert resp.status_code == 401
        resp = client.delete("/projects/p/tasks/t/comments/c")
        assert resp.status_code == 401
