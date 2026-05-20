"""
Security utilities: JWT helpers and password hashing.

Rules enforced:
- JWT algorithm is HARDCODED to HS256 — 'none' algorithm is always rejected.
- SECRET_KEY is never hardcoded — always resolved from Settings.
- Passwords are hashed with bcrypt — never stored in plaintext.

TODO(security): Implement token revocation / blocklist for logout invalidation.
TODO(security): Add MFA support before production healthcare deployment.
TODO(security): Consider upgrading to Argon2 for password hashing (more memory-hard).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

# HARDCODED — never accept 'none' or derive from token header
_ALGORITHM = "HS256"
_TOKEN_EXPIRE_MINUTES = 60

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_access_token(data: dict[str, object], secret_key: str, expires_minutes: int = _TOKEN_EXPIRE_MINUTES) -> str:
    """Create a signed JWT. Expiry is always enforced."""
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    payload["exp"] = expire
    return jwt.encode(payload, secret_key, algorithm=_ALGORITHM)


def decode_access_token(token: str, secret_key: str) -> dict[str, object]:
    """Decode and validate a JWT. Raises JWTError on any failure."""
    # algorithm is hardcoded — never read from the token header
    return jwt.decode(token, secret_key, algorithms=[_ALGORITHM])


def hash_password(plain: str) -> str:
    """Hash a password with bcrypt."""
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return _pwd_context.verify(plain, hashed)
