"""Authentication API routes and dependency guards for single-operator deployment."""

import logging
from typing import Optional
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.config import settings
from app.services.auth_service import SessionData, auth_service

logger = logging.getLogger("flamo.api.auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    success: bool = True
    authenticated: bool = True
    username: str
    csrf_token: str
    expires_at: float


class AuthStatusResponse(BaseModel):
    auth_enabled: bool
    authenticated: bool
    username: Optional[str] = None
    csrf_token: Optional[str] = None


def get_client_ip(request: Request) -> str:
    """Extract client IP address safely, checking X-Forwarded-For if behind a proxy."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "127.0.0.1"


def get_active_session(
    request: Request,
    flamo_session: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
    x_flamo_api_key: Optional[str] = Header(None),
) -> Optional[SessionData]:
    """Retrieve and validate operator session from cookie, Bearer header, or custom API key header."""
    token: Optional[str] = None

    if flamo_session:
        token = flamo_session
    elif authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    elif x_flamo_api_key:
        token = x_flamo_api_key.strip()

    if not token:
        return None

    return auth_service.get_session(token)


def require_operator(
    request: Request,
    session: Optional[SessionData] = Depends(get_active_session),
    x_csrf_token: Optional[str] = Header(None),
) -> SessionData:
    """FastAPI dependency guarding protected operator endpoints.
    
    In local loopback mode (AUTH_ENABLED=false on 127.0.0.1/localhost), loopback requests pass through.
    When AUTH_ENABLED=true or non-loopback requests arrive, valid authentication is mandatory.
    State-changing methods via cookie require valid X-CSRF-Token.
    """
    client_ip = get_client_ip(request)
    is_loopback_client = client_ip in ("127.0.0.1", "localhost", "::1", "testclient")

    # Local development bypass: only allowed on loopback when AUTH_ENABLED is explicitly false
    if not settings.auth_enabled:
        if is_loopback_client:
            # Synthetic loopback operator session for local testing
            return SessionData(
                session_id="local-loopback",
                username="local-operator",
                csrf_token="local-csrf",
                created_at=0.0,
                expires_at=float("inf"),
            )
        # Non-loopback request arriving while AUTH_ENABLED is false fails closed
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Remote access requires authentication. Set AUTH_ENABLED=true and configure operator credentials.",
        )

    # Authentication is enabled: verify session
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in with operator credentials.",
        )

    # CSRF Protection for state-changing browser cookie requests
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        # Check if request came via cookie (requires CSRF header)
        cookie_token = request.cookies.get("flamo_session")
        if cookie_token and session.session_id == cookie_token:
            if not auth_service.verify_csrf_token(session, x_csrf_token):
                logger.warning("CSRF token validation failed for operator '%s' from IP %s", session.username, client_ip)
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="CSRF token validation failed. Provide valid X-CSRF-Token header.",
                )

    return session


@router.get("/status", response_model=AuthStatusResponse)
async def get_auth_status(
    request: Request,
    session: Optional[SessionData] = Depends(get_active_session),
):
    """Public endpoint to check if authentication is enabled and get current session state."""
    client_ip = get_client_ip(request)
    is_loopback = client_ip in ("127.0.0.1", "localhost", "::1", "testclient")

    if not settings.auth_enabled:
        return AuthStatusResponse(
            auth_enabled=False,
            authenticated=is_loopback,
            username="local-operator" if is_loopback else None,
            csrf_token=None,
        )

    if session:
        return AuthStatusResponse(
            auth_enabled=True,
            authenticated=True,
            username=session.username,
            csrf_token=session.csrf_token,
        )

    return AuthStatusResponse(
        auth_enabled=True,
        authenticated=False,
        username=None,
        csrf_token=None,
    )


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, request: Request, response: Response):
    """Authenticate single operator and establish secure HttpOnly session cookie."""
    client_ip = get_client_ip(request)

    session = auth_service.authenticate_operator(
        username=req.username,
        password=req.password,
        client_ip=client_ip,
    )

    if not session:
        if auth_service.is_rate_limited(client_ip):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed login attempts. Please wait before retrying.",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid operator username or password.",
        )

    # Set secure session cookie
    response.set_cookie(
        key="flamo_session",
        value=session.session_id,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.session_expire_minutes * 60,
        path="/",
    )

    return LoginResponse(
        success=True,
        authenticated=True,
        username=session.username,
        csrf_token=session.csrf_token,
        expires_at=session.expires_at,
    )


@router.post("/logout")
async def logout(
    response: Response,
    session: Optional[SessionData] = Depends(get_active_session),
):
    """Revoke session and clear session cookie."""
    if session:
        auth_service.revoke_session(session.session_id)

    response.delete_cookie(
        key="flamo_session",
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )
    return {"success": True, "message": "Operator logged out successfully."}
