"""
Tests for /projects routes.
"""
import pytest


class TestProjectCreate:
    def test_create_project_success(self, client):
        from tests.conftest import auth_headers
        h = auth_headers(client)["headers"]
        resp = client.post("/projects", json={"name": "My Project", "description": "desc"}, headers=h)
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "My Project"
        assert body["description"] == "desc"
        assert body["status"] == "active"
        assert "id" in body
        assert "owner_id" in body

    def test_create_project_without_description(self, client):
        from tests.conftest import auth_headers
        h = auth_headers(client)["headers"]
        resp = client.post("/projects", json={"name": "No Desc"}, headers=h)
        assert resp.status_code == 201
        assert resp.json()["description"] is None

    def test_create_project_unauthenticated_401(self, client):
        resp = client.post("/projects", json={"name": "X"})
        assert resp.status_code == 401

    def test_create_project_owner_is_member(self, client, db_session):
        from tests.conftest import auth_headers
        from models import ProjectMember, ProjectMemberRole
        from sqlmodel import select
        h = auth_headers(client)["headers"]
        proj = client.post("/projects", json={"name": "P"}, headers=h).json()
        # owner should be added as member with role owner
        members = db_session.exec(select(ProjectMember).where(ProjectMember.project_id == proj["id"])).all()
        assert len(members) == 1
        assert members[0].role == ProjectMemberRole.owner


class TestProjectList:
    def test_list_empty(self, client):
        from tests.conftest import auth_headers
        h = auth_headers(client)["headers"]
        resp = client.get("/projects", headers=h)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []

    def test_list_pagination(self, client):
        from tests.conftest import auth_headers
        h = auth_headers(client)["headers"]
        for i in range(5):
            client.post("/projects", json={"name": f"P{i}"}, headers=h)
        resp = client.get("/projects?page=1&page_size=2", headers=h)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 5
        assert body["total_pages"] == 3
        assert len(body["items"]) == 2
        assert body["page"] == 1

        resp2 = client.get("/projects?page=2&page_size=2", headers=h)
        assert len(resp2.json()["items"]) == 2

        resp3 = client.get("/projects?page=3&page_size=2", headers=h)
        assert len(resp3.json()["items"]) == 1

    def test_list_search_by_name(self, client):
        from tests.conftest import auth_headers
        h = auth_headers(client)["headers"]
        client.post("/projects", json={"name": "Alpha Project"}, headers=h)
        client.post("/projects", json={"name": "Beta Project"}, headers=h)
        client.post("/projects", json={"name": "Gamma"}, headers=h)

        resp = client.get("/projects?search=Alpha", headers=h)
        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["name"] == "Alpha Project"

        # search is case-insensitive via ilike
        resp2 = client.get("/projects?search=alpha", headers=h)
        assert resp2.json()["total"] == 1

    def test_list_search_by_description(self, client):
        from tests.conftest import auth_headers
        h = auth_headers(client)["headers"]
        client.post("/projects", json={"name": "P1", "description": "special keyword"}, headers=h)
        client.post("/projects", json={"name": "P2", "description": "other"}, headers=h)
        resp = client.get("/projects?search=keyword", headers=h)
        assert resp.json()["total"] == 1

    def test_list_only_own_projects(self, client):
        from tests.conftest import auth_headers
        # user A creates project
        h_a = auth_headers(client, email="a@b.com")["headers"]
        client.post("/projects", json={"name": "A Project"}, headers=h_a)
        # user B should see 0 projects
        h_b = auth_headers(client, email="b@b.com")["headers"]
        resp = client.get("/projects", headers=h_b)
        assert resp.json()["total"] == 0

    def test_list_requires_auth(self, client):
        resp = client.get("/projects")
        assert resp.status_code == 401


class TestProjectGetUpdateDelete:
    def test_get_project_success(self, client):
        from tests.conftest import auth_headers, create_project
        h = auth_headers(client)["headers"]
        proj = create_project(client, h, name="FetchMe")
        resp = client.get(f"/projects/{proj['id']}", headers=h)
        assert resp.status_code == 200
        assert resp.json()["id"] == proj["id"]

    def test_get_project_not_found_404(self, client):
        from tests.conftest import auth_headers
        h = auth_headers(client)["headers"]
        resp = client.get("/projects/non-existent-id", headers=h)
        assert resp.status_code == 404

    def test_update_project_success(self, client):
        from tests.conftest import auth_headers, create_project
        h = auth_headers(client)["headers"]
        proj = create_project(client, h)
        resp = client.put(f"/projects/{proj['id']}", json={"name": "Updated", "status": "archived"}, headers=h)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated"
        assert resp.json()["status"] == "archived"

    def test_update_project_not_found_404(self, client):
        from tests.conftest import auth_headers
        h = auth_headers(client)["headers"]
        resp = client.put("/projects/does-not-exist", json={"name": "X"}, headers=h)
        assert resp.status_code == 404

    def test_update_project_partial(self, client):
        from tests.conftest import auth_headers, create_project
        h = auth_headers(client)["headers"]
        proj = create_project(client, h, name="Orig", description="orig desc")
        resp = client.put(f"/projects/{proj['id']}", json={"description": "new desc"}, headers=h)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Orig"
        assert resp.json()["description"] == "new desc"

    def test_delete_project_success(self, client):
        from tests.conftest import auth_headers, create_project
        h = auth_headers(client)["headers"]
        proj = create_project(client, h)
        resp = client.delete(f"/projects/{proj['id']}", headers=h)
        assert resp.status_code == 204
        # subsequent get should 404
        resp2 = client.get(f"/projects/{proj['id']}", headers=h)
        assert resp2.status_code == 404

    def test_delete_project_not_found_404(self, client):
        from tests.conftest import auth_headers
        h = auth_headers(client)["headers"]
        resp = client.delete("/projects/does-not-exist", headers=h)
        assert resp.status_code == 404

    def test_delete_requires_auth(self, client):
        resp = client.delete("/projects/some-id")
        assert resp.status_code == 401
