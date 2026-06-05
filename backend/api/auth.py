import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt as _bcrypt

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

_secret = os.getenv("JWT_SECRET_KEY")
if not _secret:
    raise RuntimeError(
        "JWT_SECRET_KEY environment variable is not set. "
        "Add it to your .env file before starting the server."
    )
SECRET_KEY: str = _secret
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24
GUEST_TOKEN_EXPIRE_HOURS = 1

bearer_scheme = HTTPBearer(auto_error=False)


# ---------- password helpers ----------

def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ---------- token helpers ----------

def create_access_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "is_guest": False,
        "exp": datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_guest_token() -> str:
    payload = {
        "sub": "guest",
        "is_guest": True,
        "exp": datetime.now(timezone.utc) + timedelta(hours=GUEST_TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ---------- FastAPI dependencies ----------

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict:
    """Requires any valid token (guest or authenticated)."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _decode_token(credentials.credentials)


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[dict]:
    """Returns token payload if present, None otherwise (fully public endpoints)."""
    if not credentials:
        return None
    try:
        return _decode_token(credentials.credentials)
    except HTTPException:
        return None


async def require_auth(user: dict = Depends(get_current_user)) -> dict:
    """Rejects guest tokens — requires a real user JWT."""
    if user.get("is_guest"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint requires an authenticated account. Please log in.",
        )
    return user
