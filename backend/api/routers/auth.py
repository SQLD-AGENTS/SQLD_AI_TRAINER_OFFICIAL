import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from api.auth import (
    create_access_token,
    create_guest_token,
    hash_password,
    require_auth,
    verify_password,
)
from api.database import AnswerLog, User, get_db
from api.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserProfileResponse,
    UserUpdateRequest,
)

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
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="비활성화된 계정입니다.",
        )
    token = create_access_token(user.user_id)
    return TokenResponse(
        access_token=token,
        is_guest=False,
        user_id=user.user_id,
        username=user.username,
    )


def _get_active_user(current_user: dict, db: Session) -> User:
    """JWT payload로 활성 사용자 DB 행을 반환. 없거나 비활성이면 예외."""
    user = db.query(User).filter(User.user_id == current_user["sub"]).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다.",
        )
    return user


@router.get("/users/me", response_model=UserProfileResponse, summary="내 프로필 조회")
def get_me(
    current_user: dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    return _get_active_user(current_user, db)


@router.put("/users/me", response_model=UserProfileResponse, summary="프로필 수정 (username·password)")
def update_me(
    body: UserUpdateRequest,
    current_user: dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    if body.username is None and body.password is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="수정할 항목(username 또는 password)을 하나 이상 입력해주세요.",
        )
    user = _get_active_user(current_user, db)
    if body.username is not None:
        user.username = body.username
    if body.password is not None:
        user.hashed_password = hash_password(body.password)
    try:
        db.commit()
        db.refresh(user)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="프로필 수정 중 오류가 발생했습니다.",
        )
    return user


@router.delete("/users/me", status_code=status.HTTP_204_NO_CONTENT, summary="계정 비활성화 (소프트 삭제)")
def delete_me(
    current_user: dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    user = _get_active_user(current_user, db)
    user.is_active = False
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="계정 비활성화 중 오류가 발생했습니다.",
        )
