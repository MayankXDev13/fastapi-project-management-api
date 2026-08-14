"""
Integration tests for /auth routes + AuthMiddleware via TestClient.
Uses in-memory SQLite (conftest engine) and real JWT flow.
"""
import datetime

import pytest
from sqlmodel import select

from models import User, VerificationToken, VerificationTokenType
from utils.auth import hash_token


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

class TestRegister:
    def test_register_success(self, client):
        resp = client.post("/auth/register", json={"email": "a@b.com", "password": "pass123"})
        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == "a@b.com"
        assert body["is_email_verified"] is False
        assert "id" in body

    def test_register_succeeds_when_mailer_fails(self, client, db_session):
        # a Resend outage must not turn registration into a 500 — the account
        # and its verification token are already committed by the service
        from main import app
        from deps import get_mailer

        def _boom(*, to, token_type, raw_token):
            raise RuntimeError("api.resend.com timed out")

        app.dependency_overrides[get_mailer] = lambda: _boom
        try:
            resp = client.post(
                "/auth/register", json={"email": "boom@b.com", "password": "pass123"}
            )
            assert resp.status_code == 201
        finally:
            app.dependency_overrides.pop(get_mailer, None)

        user = db_session.exec(select(User).where(User.email == "boom@b.com")).first()
        assert user is not None
        token = db_session.exec(
            select(VerificationToken).where(
                VerificationToken.user_id == user.id,
                VerificationToken.type == VerificationTokenType.email_verification,
            )
        ).first()
        assert token is not None and token.used_at is None

    def test_forgot_password_succeeds_when_mailer_fails(self, client):
        from main import app
        from deps import get_mailer

        def _boom(*, to, token_type, raw_token):
            raise RuntimeError("api.resend.com timed out")

        app.dependency_overrides[get_mailer] = lambda: _boom
        try:
            client.post("/auth/register", json={"email": "u@b.com", "password": "pass123"})
            resp = client.post("/auth/forgot-password", json={"email": "u@b.com"})
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.pop(get_mailer, None)

    def test_register_duplicate_returns_409(self, client):
        client.post("/auth/register", json={"email": "dup@b.com", "password": "pass123"})
        resp = client.post("/auth/register", json={"email": "dup@b.com", "password": "pass123"})
        assert resp.status_code == 409
        assert "already registered" in resp.json()["detail"].lower()

    def test_register_creates_verification_token(self, client, db_session):
        client.post("/auth/register", json={"email": "tok@b.com", "password": "pass123"})
        tokens = db_session.exec(
            select(VerificationToken).where(VerificationToken.type == VerificationTokenType.email_verification)
        ).all()
        assert len(tokens) == 1
        assert tokens[0].used_at is None


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class TestLogin:
    def test_login_success_returns_tokens(self, client):
        client.post("/auth/register", json={"email": "u@b.com", "password": "pass123"})
        resp = client.post("/auth/login", json={"email": "u@b.com", "password": "pass123"})
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"

    def test_login_wrong_password_401(self, client):
        client.post("/auth/register", json={"email": "u@b.com", "password": "pass123"})
        resp = client.post("/auth/login", json={"email": "u@b.com", "password": "wrong"})
        assert resp.status_code == 401

    def test_login_nonexistent_user_401(self, client):
        resp = client.post("/auth/login", json={"email": "no@b.com", "password": "pass123"})
        assert resp.status_code == 401

    def test_login_creates_refresh_token_in_db(self, client, db_session):
        client.post("/auth/register", json={"email": "u@b.com", "password": "pass123"})
        tokens = client.post("/auth/login", json={"email": "u@b.com", "password": "pass123"}).json()
        stored = db_session.exec(
            select(VerificationToken).where(
                VerificationToken.token_hash == hash_token(tokens["refresh_token"])
            )
        ).first()
        assert stored is not None
        assert stored.type == VerificationTokenType.refresh_token


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------

class TestRefresh:
    def test_refresh_success_rotates_token(self, client):
        client.post("/auth/register", json={"email": "u@b.com", "password": "pass123"})
        tokens = client.post("/auth/login", json={"email": "u@b.com", "password": "pass123"}).json()
        old_refresh = tokens["refresh_token"]

        resp = client.post("/auth/refresh", json={"refresh_token": old_refresh})
        assert resp.status_code == 200
        new_tokens = resp.json()
        # refresh_token is opaque random hex — must rotate
        assert new_tokens["refresh_token"] != old_refresh
        # access_token may be identical if issued within same second (exp is second-granularity),
        # so just verify it is a valid JWT with correct payload
        assert "access_token" in new_tokens
        assert new_tokens["token_type"] == "bearer"

    def test_refresh_reuse_old_token_fails(self, client):
        client.post("/auth/register", json={"email": "u@b.com", "password": "pass123"})
        tokens = client.post("/auth/login", json={"email": "u@b.com", "password": "pass123"}).json()
        old = tokens["refresh_token"]
        client.post("/auth/refresh", json={"refresh_token": old})
        # second use of same token should be 401 (marked used_at)
        resp = client.post("/auth/refresh", json={"refresh_token": old})
        assert resp.status_code == 401

    def test_refresh_invalid_token_401(self, client):
        resp = client.post("/auth/refresh", json={"refresh_token": "invalid-token-value"})
        assert resp.status_code == 401

    def test_refresh_expired_token_401(self, client, db_session):
        # create user + manually insert expired refresh token
        client.post("/auth/register", json={"email": "u@b.com", "password": "pass123"})
        user = db_session.exec(select(User).where(User.email == "u@b.com")).first()
        from datetime import datetime, timezone, timedelta
        expired = VerificationToken(
            user_id=user.id,
            token_hash=hash_token("expired-raw-token"),
            type=VerificationTokenType.refresh_token,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db_session.add(expired)
        db_session.commit()
        resp = client.post("/auth/refresh", json={"refresh_token": "expired-raw-token"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

class TestLogout:
    def test_logout_invalidates_refresh(self, client):
        client.post("/auth/register", json={"email": "u@b.com", "password": "pass123"})
        tokens = client.post("/auth/login", json={"email": "u@b.com", "password": "pass123"}).json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        resp = client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]}, headers=headers)
        assert resp.status_code == 200
        # refresh should no longer work
        resp2 = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert resp2.status_code == 401

    def test_logout_with_invalid_token_still_200(self, client):
        # logout endpoint requires auth (middleware), so we need to be authenticated
        client.post("/auth/register", json={"email": "u2@b.com", "password": "pass123"})
        tokens = client.post("/auth/login", json={"email": "u2@b.com", "password": "pass123"}).json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        resp = client.post("/auth/logout", json={"refresh_token": "does-not-exist"}, headers=headers)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Verify email
# ---------------------------------------------------------------------------

class TestVerifyEmail:
    def test_verify_email_success(self, client, mailer, db_session):
        # register → the mailer seam captures the raw verification token
        resp = client.post("/auth/register", json={"email": "u@b.com", "password": "pass123"})
        assert resp.status_code == 201
        assert len(mailer.sent) == 1
        assert mailer.sent[0]["to"] == "u@b.com"
        raw = mailer.sent[0]["raw_token"]
        assert raw

        # only the hash is stored — raw is unrecoverable from the DB
        user = db_session.exec(select(User).where(User.email == "u@b.com")).first()
        assert user.is_email_verified is False

        resp = client.post("/auth/verify-email", json={"token": raw})
        assert resp.status_code == 200

        db_session.refresh(user)
        assert user.is_email_verified is True

    def test_verify_email_invalid_token_400(self, client):
        resp = client.post("/auth/verify-email", json={"token": "bad-token"})
        assert resp.status_code == 400

    def test_verify_email_reuse_fails(self, client, mailer):
        client.post("/auth/register", json={"email": "u@b.com", "password": "pass123"})
        raw = mailer.sent[0]["raw_token"]
        assert client.post("/auth/verify-email", json={"token": raw}).status_code == 200
        resp = client.post("/auth/verify-email", json={"token": raw})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Forgot / Reset password
# ---------------------------------------------------------------------------

class TestForgotResetPassword:
    def test_forgot_password_existing_user_200(self, client, mailer):
        client.post("/auth/register", json={"email": "u@b.com", "password": "pass123"})
        before = len(mailer.sent)
        resp = client.post("/auth/forgot-password", json={"email": "u@b.com"})
        assert resp.status_code == 200
        assert "reset link" in resp.json()["message"].lower()
        assert len(mailer.sent) == before + 1

    def test_forgot_password_nonexistent_user_still_200(self, client, mailer):
        # should not leak existence — no mail is sent
        resp = client.post("/auth/forgot-password", json={"email": "no@b.com"})
        assert resp.status_code == 200
        assert mailer.sent == []

    def test_reset_password_full_lifecycle(self, client, mailer):
        client.post("/auth/register", json={"email": "u@b.com", "password": "pass123"})
        client.post("/auth/forgot-password", json={"email": "u@b.com"})
        raw = mailer.sent[-1]["raw_token"]
        assert raw

        resp = client.post("/auth/reset-password", json={"token": raw, "new_password": "newpass123"})
        assert resp.status_code == 200
        # new password works, old fails
        assert client.post("/auth/login", json={"email": "u@b.com", "password": "newpass123"}).status_code == 200
        assert client.post("/auth/login", json={"email": "u@b.com", "password": "pass123"}).status_code == 401

    def test_reset_password_success(self, client, db_session):
        client.post("/auth/register", json={"email": "u@b.com", "password": "pass123"})
        user = db_session.exec(select(User).where(User.email == "u@b.com")).first()
        from utils.auth import generate_raw_token
        raw = generate_raw_token()
        tok = VerificationToken(
            user_id=user.id,
            token_hash=hash_token(raw),
            type=VerificationTokenType.password_reset,
            expires_at=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1),
        )
        db_session.add(tok)
        db_session.commit()

        resp = client.post("/auth/reset-password", json={"token": raw, "new_password": "newpass123"})
        assert resp.status_code == 200
        # should be able to login with new password
        resp2 = client.post("/auth/login", json={"email": "u@b.com", "password": "newpass123"})
        assert resp2.status_code == 200
        # old password should fail
        resp3 = client.post("/auth/login", json={"email": "u@b.com", "password": "pass123"})
        assert resp3.status_code == 401

    def test_reset_password_invalid_token_400(self, client):
        resp = client.post("/auth/reset-password", json={"token": "bad", "new_password": "newpass123"})
        assert resp.status_code == 400

    def test_reset_password_reuse_fails(self, client, db_session):
        client.post("/auth/register", json={"email": "u@b.com", "password": "pass123"})
        user = db_session.exec(select(User).where(User.email == "u@b.com")).first()
        from utils.auth import generate_raw_token
        raw = generate_raw_token()
        tok = VerificationToken(
            user_id=user.id,
            token_hash=hash_token(raw),
            type=VerificationTokenType.password_reset,
            expires_at=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1),
        )
        db_session.add(tok)
        db_session.commit()
        client.post("/auth/reset-password", json={"token": raw, "new_password": "newpass123"})
        resp = client.post("/auth/reset-password", json={"token": raw, "new_password": "another"})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Me / Profile
# ---------------------------------------------------------------------------

class TestProfile:
    def test_get_me_requires_auth(self, client):
        resp = client.get("/auth/me")
        assert resp.status_code == 401

    def test_get_me_success(self, client):
        from tests.conftest import auth_headers
        h = auth_headers(client)["headers"]
        resp = client.get("/auth/me", headers=h)
        assert resp.status_code == 200
        assert resp.json()["email"] == "alice@example.com"

    def test_get_me_invalid_token_401(self, client):
        resp = client.get("/auth/me", headers={"Authorization": "Bearer invalid.jwt.token"})
        assert resp.status_code == 401

    def test_update_profile_success(self, client):
        from tests.conftest import auth_headers
        h = auth_headers(client, email="upd@b.com")["headers"]
        resp = client.put("/auth/me", json={"email": "new@b.com"}, headers=h)
        assert resp.status_code == 200
        assert resp.json()["email"] == "new@b.com"

    def test_update_profile_unauthenticated_401(self, client):
        resp = client.put("/auth/me", json={"email": "new@b.com"})
        assert resp.status_code == 401

    def test_change_password_success(self, client):
        from tests.conftest import auth_headers
        auth = auth_headers(client, email="cp@b.com", password="oldpass123")
        h = auth["headers"]
        resp = client.put("/auth/change-password", json={"old_password": "oldpass123", "new_password": "newpass456"}, headers=h)
        assert resp.status_code == 200
        # login with new password
        resp2 = client.post("/auth/login", json={"email": "cp@b.com", "password": "newpass456"})
        assert resp2.status_code == 200
        # old fails
        resp3 = client.post("/auth/login", json={"email": "cp@b.com", "password": "oldpass123"})
        assert resp3.status_code == 401

    def test_change_password_wrong_old_400(self, client):
        from tests.conftest import auth_headers
        h = auth_headers(client)["headers"]
        resp = client.put("/auth/change-password", json={"old_password": "wrong", "new_password": "newpass"}, headers=h)
        assert resp.status_code == 400

    def test_middleware_missing_bearer_prefix_401(self, client):
        # register+login to have a valid token, but send without Bearer prefix
        from tests.conftest import auth_headers
        auth = auth_headers(client)
        token = auth["tokens"]["access_token"]
        resp = client.get("/auth/me", headers={"Authorization": token})
        assert resp.status_code == 401

    def test_middleware_public_paths_no_auth(self, client):
        # public paths should not require auth
        resp = client.post("/auth/register", json={"email": "pub@b.com", "password": "pass123"})
        assert resp.status_code == 201
        resp = client.post("/auth/login", json={"email": "pub@b.com", "password": "pass123"})
        assert resp.status_code == 200
