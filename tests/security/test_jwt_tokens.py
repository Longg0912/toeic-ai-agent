
"""Tests for JWT access-token utilities."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest

import backend.app.security.jwt_tokens as jwt_tokens

from backend.app.security.jwt_tokens import (
    InvalidAccessTokenError,
    JWTSettings,
    create_access_token,
    decode_access_token,
)


TEST_SECRET = "test-only-secret-key-" + ("x" * 48)

TEST_SETTINGS = JWTSettings(
    secret_key=TEST_SECRET,
)


def signed_payload(token: str) -> dict:
    """Read a valid test token to prepare mutation tests."""

    return jwt.decode(
        token,
        TEST_SECRET,
        algorithms=["HS256"],
        issuer=TEST_SETTINGS.issuer,
        audience=TEST_SETTINGS.audience,
    )


def test_jwt_round_trip() -> None:
    """A valid access token returns the correct user ID."""

    token = create_access_token(
        15,
        settings=TEST_SETTINGS,
    )

    assert isinstance(token, str)
    assert len(token.split(".")) == 3

    user_id = decode_access_token(
        token,
        settings=TEST_SETTINGS,
    )

    assert user_id == 15


def test_tokens_have_unique_jti() -> None:
    """Separate tokens for one user must be distinct."""

    first = create_access_token(
        1,
        settings=TEST_SETTINGS,
    )

    second = create_access_token(
        1,
        settings=TEST_SETTINGS,
    )

    assert first != second

    assert signed_payload(first)["jti"] != (
        signed_payload(second)["jti"]
    )


def test_expired_token_is_rejected() -> None:
    """Expired JWTs must not be accepted."""

    past = datetime.now(timezone.utc) - timedelta(
        hours=2
    )

    token = create_access_token(
        1,
        settings=TEST_SETTINGS,
        now=past,
    )

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(
            token,
            settings=TEST_SETTINGS,
        )


def test_modified_token_is_rejected() -> None:
    """Changing signed token content invalidates it."""

    token = create_access_token(
        1,
        settings=TEST_SETTINGS,
    )

    header, payload, signature = token.split(".")

    modified_payload = (
        ("A" if payload[0] != "A" else "B")
        + payload[1:]
    )

    tampered = (
        f"{header}.{modified_payload}.{signature}"
    )

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(
            tampered,
            settings=TEST_SETTINGS,
        )


def test_wrong_secret_is_rejected() -> None:
    """Only the correct signing key can verify a token."""

    token = create_access_token(
        1,
        settings=TEST_SETTINGS,
    )

    other_settings = JWTSettings(
        secret_key="another-test-secret-" + ("y" * 48),
    )

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(
            token,
            settings=other_settings,
        )


def test_wrong_issuer_is_rejected() -> None:
    """Tokens from another issuer must be rejected."""

    other_settings = JWTSettings(
        secret_key=TEST_SECRET,
        issuer="another-application",
    )

    token = create_access_token(
        1,
        settings=other_settings,
    )

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(
            token,
            settings=TEST_SETTINGS,
        )


def test_wrong_audience_is_rejected() -> None:
    """Tokens intended for another API must be rejected."""

    other_settings = JWTSettings(
        secret_key=TEST_SECRET,
        audience="another-api",
    )

    token = create_access_token(
        1,
        settings=other_settings,
    )

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(
            token,
            settings=TEST_SETTINGS,
        )


def test_missing_expiry_is_rejected() -> None:
    """Every access token must contain exp."""

    token = create_access_token(
        1,
        settings=TEST_SETTINGS,
    )

    payload = signed_payload(token)
    payload.pop("exp")

    invalid_token = jwt.encode(
        payload,
        TEST_SECRET,
        algorithm="HS256",
    )

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(
            invalid_token,
            settings=TEST_SETTINGS,
        )


def test_wrong_token_type_is_rejected() -> None:
    """Refresh-type tokens must not be accepted as access tokens."""

    token = create_access_token(
        1,
        settings=TEST_SETTINGS,
    )

    payload = signed_payload(token)
    payload["type"] = "refresh"

    invalid_token = jwt.encode(
        payload,
        TEST_SECRET,
        algorithm="HS256",
    )

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(
            invalid_token,
            settings=TEST_SETTINGS,
        )


def test_malformed_token_is_rejected() -> None:
    """Malformed token strings must be rejected safely."""

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(
            "not.a.valid.jwt",
            settings=TEST_SETTINGS,
        )


def test_invalid_user_id_is_rejected() -> None:
    """Token creation requires a positive integer ID."""

    for invalid_id in (0, -1, True, "15"):
        with pytest.raises(ValueError):
            create_access_token(
                invalid_id,
                settings=TEST_SETTINGS,
            )


def test_missing_and_weak_secret_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """JWT must never use a missing or weak default key."""

    monkeypatch.setattr(
        jwt_tokens,
        "ENV_FILE",
        tmp_path / "nonexistent.env",
    )

    monkeypatch.delenv(
        "JWT_SECRET_KEY",
        raising=False,
    )

    with pytest.raises(
        RuntimeError,
        match="JWT_SECRET_KEY is missing",
    ):
        jwt_tokens.get_jwt_settings()

    with pytest.raises(
        ValueError,
        match="at least 32 bytes",
    ):
        JWTSettings(secret_key="too-short")


def test_invalid_subject_is_rejected() -> None:
    """A JWT subject must be a positive numeric user ID."""

    token = create_access_token(
        1,
        settings=TEST_SETTINGS,
    )

    payload = signed_payload(token)
    payload["sub"] = "not-a-user-id"

    invalid_token = jwt.encode(
        payload,
        TEST_SECRET,
        algorithm="HS256",
    )

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(
            invalid_token,
            settings=TEST_SETTINGS,
        )


def test_future_token_is_rejected() -> None:
    """Tokens not yet valid must be rejected."""

    future = datetime.now(timezone.utc) + timedelta(
        hours=1
    )

    token = create_access_token(
        1,
        settings=TEST_SETTINGS,
        now=future,
    )

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(
            token,
            settings=TEST_SETTINGS,
        )
