"""
Tests for /projects/{project_id}/members
"""
import pytest


def _auth_and_project(client, email="owner@b.com"):
    from tests.conftest import auth_headers, create_project
    auth = auth_headers(client, email=email)
    h = auth["headers"]
    proj = create_project(client, h)
    return h, proj["id"]


def _register_and_get_user_id(client, email):
    client.post("/auth/register", json={"email": email, "password": "pass123"})
    from sqlmodel import select
    from models import User
    # use a temporary engine query via client fixture's engine? fallback: login and get /auth/me
    # we have engine fixture separately but here we can login as that user
    resp = client.post("/auth/login", json={"email": email, "password": "pass123"})
    # decode access token to get sub? easier: use /auth/me with that user's token
    token = resp.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    return me["id"]


class TestMemberList:
    def test_list_members_contains_owner(self, client):
        h, pid = _auth_and_project(client)
        resp = client.get(f"/projects/{pid}/members", headers=h)
        assert resp.status_code == 200
        members = resp.json()
        assert len(members) == 1
        assert members[0]["role"] == "owner"

    def test_list_requires_auth_401(self, client):
        resp = client.get("/projects/pid/members")
        assert resp.status_code == 401


class TestMemberAdd:
    def test_add_member_success(self, client):
        h, pid = _auth_and_project(client)
        # create second user
        new_user_id = _register_and_get_user_id(client, "new@b.com")
        resp = client.post(f"/projects/{pid}/members", json={"user_id": new_user_id, "role": "member"}, headers=h)
        assert resp.status_code == 201
        body = resp.json()
        assert body["user_id"] == new_user_id
        assert body["project_id"] == pid
        assert body["role"] == "member"

    def test_add_member_default_role(self, client):
        h, pid = _auth_and_project(client)
        new_user_id = _register_and_get_user_id(client, "new2@b.com")
        resp = client.post(f"/projects/{pid}/members", json={"user_id": new_user_id}, headers=h)
        assert resp.status_code == 201
        assert resp.json()["role"] == "member"

    def test_add_member_duplicate_409(self, client):
        h, pid = _auth_and_project(client)
        new_user_id = _register_and_get_user_id(client, "dup@b.com")
        client.post(f"/projects/{pid}/members", json={"user_id": new_user_id}, headers=h)
        resp = client.post(f"/projects/{pid}/members", json={"user_id": new_user_id}, headers=h)
        assert resp.status_code == 409

    def test_add_member_requires_auth(self, client):
        resp = client.post("/projects/pid/members", json={"user_id": "some-id"})
        assert resp.status_code == 401

    def test_add_member_with_roles(self, client):
        h, pid = _auth_and_project(client)
        for role in ["admin", "viewer"]:
            uid = _register_and_get_user_id(client, f"{role}@b.com")
            resp = client.post(f"/projects/{pid}/members", json={"user_id": uid, "role": role}, headers=h)
            assert resp.status_code == 201
            assert resp.json()["role"] == role


class TestMemberUpdateRole:
    def test_update_role_success(self, client):
        h, pid = _auth_and_project(client)
        uid = _register_and_get_user_id(client, "member@b.com")
        client.post(f"/projects/{pid}/members", json={"user_id": uid, "role": "member"}, headers=h)
        resp = client.put(f"/projects/{pid}/members/{uid}", json={"new_role": "admin"}, headers=h)
        assert resp.status_code == 200
        assert resp.json()["role"] == "admin"

    def test_update_role_not_found_404(self, client):
        h, pid = _auth_and_project(client)
        resp = client.put(f"/projects/{pid}/members/non-existent", json={"new_role": "admin"}, headers=h)
        assert resp.status_code == 404

    def test_update_role_requires_auth(self, client):
        resp = client.put("/projects/pid/members/uid", json={"new_role": "admin"})
        assert resp.status_code == 401


class TestMemberRemove:
    def test_remove_member_success(self, client):
        h, pid = _auth_and_project(client)
        uid = _register_and_get_user_id(client, "rem@b.com")
        client.post(f"/projects/{pid}/members", json={"user_id": uid}, headers=h)
        resp = client.delete(f"/projects/{pid}/members/{uid}", headers=h)
        assert resp.status_code == 200
        assert "removed" in resp.json()["message"].lower()
        # list should now have only owner again
        members = client.get(f"/projects/{pid}/members", headers=h).json()
        assert len(members) == 1

    def test_remove_member_not_found_404(self, client):
        h, pid = _auth_and_project(client)
        resp = client.delete(f"/projects/{pid}/members/not-exist", headers=h)
        assert resp.status_code == 404

    def test_remove_requires_auth(self, client):
        resp = client.delete("/projects/pid/members/uid")
        assert resp.status_code == 401
