import os
import uuid

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from api.auth import (
    create_access_token,
    create_guest_token,
    generate_temp_password,
    hash_password,
    require_auth,
    verify_google_access_token,
    verify_password,
)
from api.database import AnswerLog, User, get_db
from api.schemas.auth import (
    DeleteRequest,
    EmailCheckResponse,
    FindUsernameRequest,
    FindUsernameResponse,
    GoogleLoginRequest,
    GoogleLoginResponse,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    ResetPasswordResponse,
    TokenResponse,
    UsernameCheckResponse,
    UserProfileResponse,
    UserUpdateRequest,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID", "")
_R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "")
_R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "")
_R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "")
_R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "").rstrip("/")


def _r2_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{_R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=_R2_ACCESS_KEY_ID,
        aws_secret_access_key=_R2_SECRET_ACCESS_KEY,
        region_name="auto",
    )


# ── helpers ──────────────────────────────────────────────────────────────────

def _get_active_user(current_user: dict, db: Session) -> User:
    """JWT payload로 활성 사용자 DB 행을 반환. 없거나 비활성이면 예외."""
    user = db.query(User).filter(User.user_id == current_user["sub"]).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다.",
        )
    # token_version 검증 — tv 클레임이 있는 토큰에만 적용 (기존 토큰 하위 호환)
    if "tv" in current_user and current_user["tv"] != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="세션이 만료되었습니다. 다시 로그인해주세요.",
        )
    return user


# ── public endpoints ─────────────────────────────────────────────────────────

@router.post("/guest", response_model=TokenResponse, summary="게스트 토큰 발급")
def issue_guest_token():
    token = create_guest_token()
    return TokenResponse(access_token=token, is_guest=True)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED, summary="회원가입")
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 사용 중인 이메일입니다.")
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 사용 중인 사용자명입니다.")
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
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 사용 중인 이메일 또는 사용자명입니다.")
    except Exception:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="회원가입 처리 중 오류가 발생했습니다.")
    token = create_access_token(user.user_id, user.token_version)
    return TokenResponse(access_token=token, is_guest=False, user_id=user.user_id, username=user.username, avatar_url=user.avatar_url)


@router.post("/login", response_model=TokenResponse, summary="로그인")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="이메일 또는 비밀번호가 올바르지 않습니다.")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="비활성화된 계정입니다.")
    token = create_access_token(user.user_id, user.token_version)
    return TokenResponse(access_token=token, is_guest=False, user_id=user.user_id, username=user.username, avatar_url=user.avatar_url)


@router.post("/google", response_model=GoogleLoginResponse, summary="구글 소셜 로그인")
def google_login(body: GoogleLoginRequest, db: Session = Depends(get_db)):
    payload = verify_google_access_token(body.access_token)
    google_sub = payload["sub"]
    email = payload.get("email", "")
    name = payload.get("name", email.split("@")[0] if email else "Google User")
    picture = payload.get("picture")

    is_new_user = False

    # 1. 이미 소셜 연결된 계정 재로그인
    user = db.query(User).filter(User.social_id == google_sub, User.is_active == True).first()
    if not user:
        # 2. 동일 이메일 기존 계정 → 소셜 정보 연결 (계정 병합)
        if email:
            user = db.query(User).filter(User.email == email, User.is_active == True).first()
        if user:
            user.social_provider = "google"
            user.social_id = google_sub
            if not user.avatar_url and picture:
                user.avatar_url = picture
            try:
                db.commit()
                db.refresh(user)
            except Exception:
                db.rollback()
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="계정 연결 중 오류가 발생했습니다.")
        else:
            # 3. 신규 계정 생성
            is_new_user = True
            username = name[:20] if name else "GoogleUser"
            # username 중복 시 숫자 접미사 추가
            base_username = username
            suffix = 1
            while db.query(User).filter(User.username == username).first():
                username = f"{base_username}{suffix}"
                suffix += 1
            user = User(
                user_id=str(uuid.uuid4()),
                email=email,
                username=username,
                hashed_password=None,
                avatar_url=picture,
                social_provider="google",
                social_id=google_sub,
            )
            try:
                db.add(user)
                db.commit()
                db.refresh(user)
            except IntegrityError:
                db.rollback()
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 사용 중인 이메일입니다.")
            except Exception:
                db.rollback()
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="회원가입 처리 중 오류가 발생했습니다.")

    token = create_access_token(user.user_id, user.token_version)
    return GoogleLoginResponse(
        access_token=token,
        is_guest=False,
        user_id=user.user_id,
        username=user.username,
        is_new_user=is_new_user,
        avatar_url=user.avatar_url,
    )


@router.get("/check-email", response_model=EmailCheckResponse, summary="이메일 중복 확인")
def check_email(email: str = Query(...), db: Session = Depends(get_db)):
    exists = db.query(User).filter(User.email == email, User.is_active == True).first()
    return EmailCheckResponse(available=exists is None)


@router.get("/check-username", response_model=UsernameCheckResponse, summary="사용자명 중복 확인")
def check_username(username: str = Query(...), db: Session = Depends(get_db)):
    exists = db.query(User).filter(User.username == username, User.is_active == True).first()
    return UsernameCheckResponse(available=exists is None)


@router.post("/find-username", response_model=FindUsernameResponse, summary="아이디(사용자명) 찾기")
def find_username(body: FindUsernameRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="해당 이메일로 가입된 계정이 없습니다.")
    return FindUsernameResponse(username=user.username)


@router.post("/reset-password", response_model=ResetPasswordResponse, summary="임시 비밀번호 발급")
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="해당 이메일로 가입된 계정이 없습니다.")
    temp_pw = generate_temp_password()
    user.hashed_password = hash_password(temp_pw)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="비밀번호 재설정 중 오류가 발생했습니다.")
    return ResetPasswordResponse(temp_password=temp_pw)


# ── authenticated endpoints ───────────────────────────────────────────────────

@router.get("/users/me", response_model=UserProfileResponse, summary="내 프로필 조회")
def get_me(current_user: dict = Depends(require_auth), db: Session = Depends(get_db)):
    return _get_active_user(current_user, db)


@router.put("/users/me", response_model=UserProfileResponse, summary="프로필 수정")
def update_me(
    body: UserUpdateRequest,
    current_user: dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    if body.username is None and body.password is None and body.email is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="수정할 항목(username, email, password)을 하나 이상 입력해주세요.",
        )
    user = _get_active_user(current_user, db)

    # 비밀번호 변경 시 현재 비밀번호 필수 검증 (소셜 전용 계정은 최초 설정 허용)
    if body.password is not None:
        if user.hashed_password:
            if not body.current_password:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="비밀번호를 변경하려면 현재 비밀번호를 입력해주세요.",
                )
            if not verify_password(body.current_password, user.hashed_password):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="현재 비밀번호가 올바르지 않습니다.",
                )
        user.hashed_password = hash_password(body.password)

    if body.username is not None:
        duplicate = db.query(User).filter(
            User.username == body.username,
            User.user_id != user.user_id,
        ).first()
        if duplicate:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 사용 중인 사용자명입니다.")
        user.username = body.username

    if body.email is not None:
        duplicate = db.query(User).filter(
            User.email == body.email,
            User.user_id != user.user_id,
        ).first()
        if duplicate:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 사용 중인 이메일입니다.")
        user.email = body.email

    try:
        db.commit()
        db.refresh(user)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="프로필 수정 중 오류가 발생했습니다.")
    return user


@router.delete("/users/me", status_code=status.HTTP_204_NO_CONTENT, summary="계정 비활성화 (소프트 삭제)")
def delete_me(
    body: DeleteRequest,
    current_user: dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    user = _get_active_user(current_user, db)
    if user.hashed_password:
        if not body.password:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="비밀번호를 입력해주세요.",
            )
        if not verify_password(body.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="비밀번호가 올바르지 않습니다.",
            )
    user.is_active = False
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="계정 비활성화 중 오류가 발생했습니다.")


@router.post("/users/me/revoke-all", response_model=TokenResponse, summary="모든 기기 로그아웃")
def revoke_all_sessions(
    current_user: dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """token_version을 올려 기존 토큰을 모두 무효화하고 현재 세션용 새 토큰을 반환."""
    user = _get_active_user(current_user, db)
    user.token_version = (user.token_version or 0) + 1
    try:
        db.commit()
        db.refresh(user)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="세션 무효화 중 오류가 발생했습니다.")
    new_token = create_access_token(user.user_id, user.token_version)
    return TokenResponse(access_token=new_token, is_guest=False, user_id=user.user_id, username=user.username)


@router.post("/users/me/avatar", response_model=UserProfileResponse, summary="프로필 사진 업로드")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    if file.content_type not in ("image/jpeg", "image/png"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="JPG 또는 PNG 파일만 허용됩니다.")
    contents = await file.read()
    if len(contents) > 2 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="파일 크기는 2MB 이하여야 합니다.")

    user = _get_active_user(current_user, db)
    ext = "jpg" if file.content_type == "image/jpeg" else "png"
    object_key = f"avatars/{user.user_id}.{ext}"

    try:
        _r2_client().put_object(
            Bucket=_R2_BUCKET_NAME,
            Key=object_key,
            Body=contents,
            ContentType=file.content_type,
        )
    except (BotoCoreError, ClientError) as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"스토리지 업로드 실패: {e}")

    user.avatar_url = f"{_R2_PUBLIC_URL}/{object_key}"
    try:
        db.commit()
        db.refresh(user)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="프로필 사진 저장 중 오류가 발생했습니다.")
    return user


@router.delete("/users/me/avatar", response_model=UserProfileResponse, summary="프로필 사진 삭제")
def delete_avatar(
    current_user: dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    user = _get_active_user(current_user, db)
    if user.avatar_url and _R2_PUBLIC_URL and user.avatar_url.startswith(_R2_PUBLIC_URL):
        object_key = user.avatar_url[len(_R2_PUBLIC_URL) + 1:]
        try:
            _r2_client().delete_object(Bucket=_R2_BUCKET_NAME, Key=object_key)
        except (BotoCoreError, ClientError):
            pass
    user.avatar_url = None
    try:
        db.commit()
        db.refresh(user)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="프로필 사진 삭제 중 오류가 발생했습니다.")
    return user
