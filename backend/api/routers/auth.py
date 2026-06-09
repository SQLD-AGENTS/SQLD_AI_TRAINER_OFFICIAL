import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.auth import (
    create_access_token,
    create_guest_token,
    hash_password,
    verify_password,
)
from api.database import AnswerLog, User, get_db
from api.schemas.auth import LoginRequest, RegisterRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/guest", response_model=TokenResponse, summary="게스트 토큰 발급")
def issue_guest_token():
    """
    로그인 없이 문제 풀이를 시작할 수 있는 1시간짜리 게스트 토큰을 발급합니다.
    게스트는 문제 조회·해설 조회만 가능하며 데이터는 저장되지 않습니다.
    """
    token = create_guest_token()
    return TokenResponse(access_token=token, is_guest=True)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED, summary="회원가입")
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 사용 중인 이메일입니다.",
        )
    user = User(
        user_id=str(uuid.uuid4()),
        email=body.email,
        username=body.username,
        hashed_password=hash_password(body.password),
    )
    try:
        db.add(user)
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 사용 중인 이메일입니다.",
        )
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="회원가입 처리 중 오류가 발생했습니다.",
        )
    token = create_access_token(user.user_id)
    return TokenResponse(
        access_token=token,
        is_guest=False,
        user_id=user.user_id,
        username=user.username,
    )


@router.post("/login", response_model=TokenResponse, summary="로그인")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이메일 또는 비밀번호가 올바르지 않습니다.",
        )
    token = create_access_token(user.user_id)
    return TokenResponse(
        access_token=token,
        is_guest=False,
        user_id=user.user_id,
        username=user.username,
    )
