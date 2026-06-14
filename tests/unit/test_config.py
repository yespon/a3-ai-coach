"""Settings normalization tests."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_auth_mode_normalizes_whitespace_and_case():
    settings = Settings(auth_mode=" SSO ")
    assert settings.auth_mode == "sso"


@pytest.mark.parametrize("mode", ["sso", "local", "both"])
def test_auth_mode_accepts_known_values(mode: str):
    settings = Settings(auth_mode=mode)
    assert settings.auth_mode == mode


def test_auth_mode_rejects_unknown_value():
    with pytest.raises(ValidationError):
        Settings(auth_mode="password")
