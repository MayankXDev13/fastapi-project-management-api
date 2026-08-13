"""
Unit tests for utils/auth.py — hashing, JWT, opaque token hashing.
Covers: hash_password / verify_password, create_access_token / decode_token,
        generate_raw_token / hash_token, create_refresh_token (if used).
"""
import time
from datetime import timedelta, timezone, datetime

import jwt
import pytest

from utils.auth import (
    hash_password,
    verify_password,
    create_access_token,
    decode_token,
    generate_raw_token,
    hash_token,
)
from config import SECRET_KEY, ALGORITHM


# ---------------------------------------------------------------------------
# password hashing
# ---------------------------------------------------------------------------

class TestHashPassword:
    def test_hash_and_verify_success(self):
        hashed = hash_password("mysecret")
        assert hashed != "mysecret"
        assert verify_password("mysecret", hashed) is True

    def test_verify_wrong_password_fails(self):
        hashed = hash_password("correct")
        assert verify_password("wrong", hashed) is False

    def test_hash_is_salted(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2  # bcrypt salt => different hashes


# ---------------------------------------------------------------------------
# JWT — create_access_token / decode_token
# ---------------------------------------------------------------------------

class TestAccessToken:
    def test_create_and_decode(self):
        token = create_access_token({"sub": "user-123"})
        payload = decode_token(token)
        assert payload["sub"] == "user-123"
        assert payload["type"] == "access"
        assert "exp" in payload

    def test_exp_is_future(self):
        token = create_access_token({"sub": "u1"})
        payload = decode_token(token)
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        assert exp > datetime.now(timezone.utc)

    def test_custom_expiry(self):
        token = create_access_token({"sub": "u1"}, expires_delta=timedelta(seconds=1))
        payload = decode_token(token)
        assert payload["sub"] == "u1"
        # wait for expiry
        time.sleep(1.5)
        try:
            decode_token(token)
            assert False, "Expired token should raise"
        except jwt.ExpiredSignatureError:
            pass

    def test_invalid_token_raises(self):
        with pytest.raises(jwt.InvalidTokenError):
            decode_token("not.a.jwt")

    def test_tampered_token_raises(self):
        token = create_access_token({"sub": "u1"})
        tampered = token[:-4] + "abcd"
        with pytest.raises(jwt.InvalidTokenError):
            decode_token(tampered)

    def test_wrong_secret_fails(self):
        token = jwt.encode({"sub": "u1", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}, "wrong-secret-but-long-enough-for-hs256-32-chars!!", algorithm=ALGORITHM)
        with pytest.raises(jwt.InvalidSignatureError):
            decode_token(token)


# ---------------------------------------------------------------------------
# Opaque token helpers (VerificationToken)
# ---------------------------------------------------------------------------

class TestOpaqueTokens:
    def test_generate_raw_token_length(self):
        t = generate_raw_token()
        assert len(t) == 64  # token_hex(32) => 64 hex chars
        assert all(c in "0123456789abcdef" for c in t)

    def test_generate_raw_token_unique(self):
        assert generate_raw_token() != generate_raw_token()

    def test_hash_token_deterministic(self):
        assert hash_token("abc") == hash_token("abc")

    def test_hash_token_is_sha256_hex(self):
        h = hash_token("hello")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_different_inputs_different_hashes(self):
        assert hash_token("a") != hash_token("b")
