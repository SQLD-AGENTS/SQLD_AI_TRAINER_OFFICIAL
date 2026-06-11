import os
import random
import string
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt as _bcrypt
import requests as http_requests
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests

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

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")


# ---------- Google OAuth helpers ----------

def verify_google_id_token(token: str) -> dict:
    """Google id_token을 공개키로 검증하고 payload를 반환한다.
    반환값: {"sub": ..., "email": ..., "name": ..., "picture": ...}
    """
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="서버에 GOOGLE_CLIENT_ID 환경변수가 설정되지 않았습니다.",
        )
    try:
        idinfo = google_id_token.verify_oauth2_token(
            token, google_requests.Request(), GOOGLE_CLIENT_ID
        )
        return idinfo
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"유효하지 않은 Google ID 토큰입니다: {e}",
        )


def verify_google_access_token(access_token: str) -> dict:
    """Google access_token으로 userinfo 엔드포인트를 호출해 사용자 정보를 반환한다.
    반환값: {"sub": ..., "email": ..., "name": ..., "picture": ...}
    """
    try:
        resp = http_requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="유효하지 않은 Google 액세스 토큰입니다.",
            )
        return resp.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Google 인증 중 오류가 발생했습니다: {e}",
        )


# ---------- password helpers ----------

def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def generate_temp_password(length: int = 10) -> str:
    chars = string.ascii_letters + string.digits + "!@#$%"
    required = [
        random.choice(string.ascii_uppercase),
        random.choice(string.ascii_lowercase),
        random.choice(string.digits),
        random.choice("!@#$%"),
    ]
    rest = [random.choice(chars) for _ in range(length - len(required))]
    pool = required + rest
    random.shuffle(pool)
    return "".join(pool)


# ---------- token helpers ----------

def create_access_token(user_id: str, token_version: int = 0) -> str:
    payload = {
        "sub": user_id,
        "is_guest": False,
        "tv": token_version,
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
