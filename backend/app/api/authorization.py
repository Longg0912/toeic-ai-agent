
"""Role-based authorization dependencies.

Supported roles:
- student
- admin

Authentication is delegated to get_current_user().
Role checks use the user's current database role,
not untrusted request data or JWT role claims.
"""

from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, status

from backend.app.api.auth_deps import get_current_user
from backend.app.db.models import User


# Supported roles in the current project.
UserRole = Literal["student", "admin"]

SUPPORTED_ROLES = frozenset({
    "student",
    "admin",
})


def require_role(
    *allowed_roles: UserRole,
) -> Callable[..., User]:
    """Create a FastAPI dependency requiring specific roles.

    Example:
        Depends(require_role("admin"))

        Depends(require_role("student", "admin"))

    Raises:
        ValueError:
            If no roles or unsupported roles are configured.

    Returns:
        A dependency returning the authenticated User
        when their database role is permitted.
    """

    if not allowed_roles:
        raise ValueError(
            "At least one allowed role is required."
        )

    allowed_role_set = frozenset(allowed_roles)

    if not allowed_role_set.issubset(SUPPORTED_ROLES):
        raise ValueError(
            "Unsupported role in require_role()."
        )

    def role_dependency(
        current_user: Annotated[
            User,
            Depends(get_current_user),
        ],
    ) -> User:
        """Check the authenticated user's current role."""

        if current_user.role not in allowed_role_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions.",
            )

        return current_user

    return role_dependency
