"""Unit tests for the identity dependency: authenticate() + get_current_user."""
import pytest
from fastapi import HTTPException
from sqlmodel import Session

from deps import authenticate
from models import User
from utils.auth import create_access_token


def _make_user(db: Session, email: str = "auth@x.com") -> User:
    user = User(email=email, hash_password="x")
    db.add(user)
    db.commit()
    return user


class _FakeRequest:
    def __init__(self, headers: dict | None = None):
        self.headers = headers or {}


class TestAuthenticate:
    def test_valid_bearer_returns_user(self, db_session):
        user = _make_user(db_session)
        token = create_access_token({"sub": user.id})
        req = _FakeRequest({"Authorization": f"Bearer {token}"})
        assert authenticate(req, db_session).id == user.id

    def test_no_header_returns_none(self, db_session):
        assert authenticate(_FakeRequest(), db_session) is None

    def test_non_bearer_scheme_returns_none(self, db_session):
        req = _FakeRequest({"Authorization": "Basic abc"})
        assert authenticate(req, db_session) is None

    def test_empty_token_returns_none(self, db_session):
        req = _FakeRequest({"Authorization": "Bearer "})
        assert authenticate(req, db_session) is None

    def test_garbage_token_returns_none(self, db_session):
        req = _FakeRequest({"Authorization": "Bearer not.a.jwt"})
        assert authenticate(req, db_session) is None

    def test_unknown_user_returns_none(self, db_session):
        token = create_access_token({"sub": "no-such-user"})
        req = _FakeRequest({"Authorization": f"Bearer {token}"})
        assert authenticate(req, db_session) is None

    def test_token_without_sub_returns_none(self, db_session):
        token = create_access_token({"role": "admin"})
        req = _FakeRequest({"Authorization": f"Bearer {token}"})
        assert authenticate(req, db_session) is None


class TestGetCurrentUser401:
    """get_current_user is exercised end-to-end through protected routes."""

    def test_no_token_401_with_bearer_challenge(self, client):
        resp = client.get("/auth/me")
        assert resp.status_code == 401
        assert resp.headers.get("WWW-Authenticate") == "Bearer"

    def test_invalid_token_401(self, client):
        resp = client.get("/auth/me", headers={"Authorization": "Bearer invalid.jwt.token"})
        assert resp.status_code == 401

    def test_deleted_user_401(self, client, db_session):
        from tests.conftest import auth_headers

        auth = auth_headers(client, email="ghost@x.com")
        user = db_session.exec(
            __import__("sqlmodel").select(User).where(User.email == "ghost@x.com")
        ).one()
        db_session.delete(user)
        db_session.commit()
        resp = client.get("/auth/me", headers=auth["headers"])
        assert resp.status_code == 401


class TestLogoutRequiresAuth:
    def test_logout_without_token_401(self, client):
        resp = client.post("/auth/logout", json={"refresh_token": "whatever"})
        assert resp.status_code == 401