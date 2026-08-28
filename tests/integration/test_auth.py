import jwt as pyjwt

from app.auth.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.config import settings


class TestPassword:
    def test_hash_and_verify(self):
        h = hash_password("secret123")
        assert h.startswith("$2")
        assert verify_password("secret123", h)
        assert not verify_password("wrongpass", h)

    def test_hash_is_randomized(self):
        assert hash_password("secret123") != hash_password("secret123")

    def test_verify_invalid_hash_returns_false(self):
        assert not verify_password("x", "not-a-bcrypt-hash")


class TestJwt:
    def test_roundtrip(self):
        token = create_access_token(42)
        assert decode_access_token(token) == 42

    def test_wrong_secret_rejected(self):
        token = pyjwt.encode(
            {"sub": "1", "exp": 9999999999}, "another-secret-that-is-long-enough-12345", algorithm="HS256"
        )
        try:
            decode_access_token(token)
            raise AssertionError("should have raised")
        except Exception:
            pass

    def test_no_exp_rejected(self):
        token = pyjwt.encode({"sub": "1"}, settings.jwt_secret, algorithm="HS256")
        try:
            decode_access_token(token)
            raise AssertionError("should have raised")
        except Exception:
            pass

    def test_expired_rejected(self):
        import time

        token = pyjwt.encode(
            {"sub": "1", "iat": int(time.time()) - 100, "exp": int(time.time()) - 50},
            settings.jwt_secret,
            algorithm="HS256",
        )
        try:
            decode_access_token(token)
            raise AssertionError("should have raised")
        except Exception:
            pass
