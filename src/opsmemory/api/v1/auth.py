"""Authentication endpoints: login, logout, current user."""

from typing import Annotated

from fastapi import APIRouter, Header

from opsmemory.api.dependencies import AuthServiceDep, CurrentUserDep
from opsmemory.api.schemas.auth import LoginRequest, LoginResponse, UserOut
from opsmemory.auth.service import AuthError
from opsmemory.core.errors import ValidationFailedError

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, auth: AuthServiceDep) -> LoginResponse:
    """Authenticate with email + password and open a session."""
    result = await auth.login(payload.email, payload.password)
    return LoginResponse(
        token=result.token,
        expires_at=result.expires_at,
        user=UserOut.model_validate(result.user),
    )


@router.post("/logout", status_code=204)
async def logout(
    auth: AuthServiceDep,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Revoke the current session token."""
    if authorization and authorization.lower().startswith("bearer "):
        await auth.logout(authorization[7:].strip())


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUserDep) -> UserOut:
    """Return the currently authenticated user.

    When auth is disabled, no user is attached — surface that explicitly.
    """
    if user is None:
        raise ValidationFailedError(
            "Authentication is disabled on this deployment", code="AUTH_DISABLED"
        )
    return UserOut.model_validate(user)


__all__ = ["AuthError", "router"]
