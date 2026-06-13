"""Unit tests for password hashing utilities."""

from app.core.security import hash_password, verify_password


def test_hash_and_verify_password():
    hashed = hash_password("secret123")
    assert verify_password("secret123", hashed) is True


def test_verify_wrong_password():
    hashed = hash_password("secret123")
    assert verify_password("wrong", hashed) is False


def test_hash_produces_different_salts():
    h1 = hash_password("same_password")
    h2 = hash_password("same_password")
    assert h1 != h2  # Different salts each time
    assert verify_password("same_password", h1) is True
    assert verify_password("same_password", h2) is True
