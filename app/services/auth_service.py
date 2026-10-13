"""Authentication, session management, and rate limiting for FLAMO single-operator deployment."""

import hashlib
import hmac
import logging
import os
import secrets
import time
from typing import Dict, List, Optional
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger("flamo.auth")


def hash_password(password: str, salt: Optional[bytes] = None, iterations: int = 100_000) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with cryptographically random salt."""
    if salt is None:
        salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${dk.hex()}"


def verify_password(password: str, hash_string: str) -> bool:
    """Verify plaintext password against PBKDF2-HMAC-SHA256 hash or configured string in constant time."""
    if not password or not hash_string:
        return False

    if hash_string.startswith("pbkdf2_sha256$"):
        parts = hash_string.split("$")
        if len(parts) != 4:
            return False
        try:
            iterations = int(parts[1])
            salt = bytes.fromhex(parts[2])
            expected_dk = bytes.fromhex(parts[3])
            actual_dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
            return secrets.compare_digest(actual_dk, expected_dk)
        except Exception as e:
            logger.warning("Error verifying password hash: %s", e)
            return False

    # Constant-time comparison fallback for plain string comparison in test environments
    return secrets.compare_digest(password.encode("utf-8"), hash_string.encode("utf-8"))


class SessionData(BaseModel):
    """Authenticated operator session representation."""
    session_id: str
    username: str
    csrf_token: str
    created_at: float
    expires_at: float


class AuthService:
    """Manages single-operator authentication, session lifecycle, CSRF tokens, and rate limits."""

    def __init__(self) -> None:
        self._sessions: Dict[str, SessionData] = {}
        self._failed_attempts: Dict[str, List[float]] = {}

    def is_rate_limited(
        self, client_ip: str, max_attempts: Optional[int] = None, window_seconds: Optional[int] = None
    ) -> bool:
        """Check if client IP has exceeded bounded login attempts within rate limit window."""
        now = time.time()
        window = window_seconds if window_seconds is not None else settings.rate_limit_window_seconds
        limit = max_attempts if max_attempts is not None else settings.rate_limit_login_attempts

        attempts = [t for t in self._failed_attempts.get(client_ip, []) if now - t < window]
        self._failed_attempts[client_ip] = attempts
        return len(attempts) >= limit

    def check_rate_limit(
        self, client_ip: str, max_attempts: Optional[int] = None, window_seconds: Optional[int] = None
    ) -> bool:
        """Return True if request is allowed, False if rate limited."""
        return not self.is_rate_limited(client_ip, max_attempts=max_attempts, window_seconds=window_seconds)

    def record_failed_attempt(self, client_ip: str) -> None:
        """Record a failed login attempt timestamp for client IP."""
        now = time.time()
        if client_ip not in self._failed_attempts:
            self._failed_attempts[client_ip] = []
        self._failed_attempts[client_ip].append(now)

    def record_login_failure(self, client_ip: str) -> None:
        """Alias for record_failed_attempt."""
        self.record_failed_attempt(client_ip)

    def reset_failed_attempts(self, client_ip: str) -> None:
        """Clear failed login attempts for client IP upon successful authentication."""
        self._failed_attempts.pop(client_ip, None)

    def clear_rate_limit(self, client_ip: str) -> None:
        """Alias for reset_failed_attempts."""
        self.reset_failed_attempts(client_ip)

    def create_session(self, username: str, expire_minutes: Optional[int] = None) -> SessionData:
        """Create and register an active operator session with CSRF token."""
        duration = expire_minutes if expire_minutes is not None else settings.session_expire_minutes
        now = time.time()
        expires = now + (duration * 60)
        session_id = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)

        session = SessionData(
            session_id=session_id,
            username=username.strip(),
            csrf_token=csrf_token,
            created_at=now,
            expires_at=expires,
        )
        self._sessions[session_id] = session
        return session

    def authenticate_operator(self, username: str, password: str, client_ip: str = "127.0.0.1") -> Optional[SessionData]:
        """Authenticate single operator and generate session with CSRF protection."""
        if self.is_rate_limited(client_ip):
            logger.warning("Login rate limit exceeded for client IP %s", client_ip)
            return None

        configured_user = settings.operator_username
        configured_hash = settings.operator_password_hash
        configured_plain = settings.operator_password

        # Determine target hash to verify
        target_hash = configured_hash or configured_plain
        if not target_hash:
            logger.warning("No operator password or password hash configured in settings.")
            self.record_failed_attempt(client_ip)
            return None

        # Verify username and password
        user_match = secrets.compare_digest(username.strip(), configured_user.strip())
        password_match = verify_password(password.strip(), target_hash)

        if not (user_match and password_match):
            self.record_failed_attempt(client_ip)
            logger.warning("Failed login attempt for user '%s' from IP %s", username, client_ip)
            return None

        # Reset failed attempts on success
        self.reset_failed_attempts(client_ip)
        session = self.create_session(username.strip())
        logger.info("Operator '%s' successfully authenticated from IP %s", username, client_ip)
        return session

    def get_session(self, session_id: str) -> Optional[SessionData]:
        """Retrieve active session if not expired."""
        if not session_id or session_id not in self._sessions:
            return None

        session = self._sessions[session_id]
        if time.time() > session.expires_at:
            self._sessions.pop(session_id, None)
            return None

        return session

    def revoke_session(self, session_id: str) -> bool:
        """Revoke active operator session upon logout."""
        if session_id in self._sessions:
            self._sessions.pop(session_id, None)
            return True
        return False

    def verify_csrf_token(self, session: SessionData, provided_token: Optional[str]) -> bool:
        """Verify CSRF token matches session CSRF token in constant time."""
        if not provided_token:
            return False
        return secrets.compare_digest(session.csrf_token, provided_token.strip())

    def validate_csrf(self, session_id: str, provided_token: Optional[str]) -> bool:
        """Validate CSRF token given session ID."""
        session = self.get_session(session_id)
        if not session:
            return False
        return self.verify_csrf_token(session, provided_token)


auth_service = AuthService()
