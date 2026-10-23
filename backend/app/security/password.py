
"""Password hashing and verification utilities.

The application uses Argon2id through pwdlib.

Plaintext passwords must never be stored in the database
or written to application logs.
"""

from argon2.exceptions import (
    InvalidHashError,
    VerificationError,
)
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError


# Create one reusable password hasher.
_password_hasher = PasswordHash.recommended()


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password with Argon2id.

    Args:
        plain_password: Password provided by the user.

    Returns:
        An encoded password hash containing algorithm
        parameters and a randomly generated salt.

    Raises:
        TypeError: If password is not a string.
        ValueError: If password is empty.
    """

    if not isinstance(plain_password, str):
        raise TypeError("Password must be a string.")

    if plain_password == "":
        raise ValueError("Password cannot be empty.")

    return _password_hasher.hash(plain_password)


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    """Verify a plaintext password against a stored hash.

    Args:
        plain_password: Password entered by the user.
        hashed_password: Previously stored encoded hash.

    Returns:
        True if the password matches, otherwise False.
    """

    if not isinstance(plain_password, str):
        return False

    if not isinstance(hashed_password, str):
        return False

    if not plain_password or not hashed_password:
        return False

    try:
        return _password_hasher.verify(
            plain_password,
            hashed_password,
        )

    except (
        UnknownHashError,
        InvalidHashError,
        VerificationError,
    ):
        # Reject unrecognized or corrupted hashes.
        # Do not expose hash values in error messages.
        return False
