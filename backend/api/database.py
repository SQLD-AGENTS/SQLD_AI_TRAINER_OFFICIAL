"""
DB 설정 + ORM 모델.

변경점 (SQLite → Postgres 선택):
- DATABASE_URL 환경변수 우선, 없으면 로컬 SQLite 폴백 (로컬 개발 무중단)
- Railway/Heroku 계열이 주는 'postgres://' 스킴을 'postgresql://'로 자동 보정
- check_same_thread 는 SQLite 전용 옵션이라 Postgres에는 전달하지 않음
- 신규 Question 테이블: 문제 마스터(datasets/json + features 산출 19컬럼 + choices)를 적재
- AnswerLog.question_id 에 FK(questions.question_id) 부여 → 정합성 보장
"""
import datetime
import os
import pathlib
import uuid

from dotenv import load_dotenv
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    create_engine,
    text,
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.types import JSON  # SQLite=JSON(TEXT) / Postgres=JSONB 로 매핑됨

# pgvector — Postgres 전용 벡터 타입. 미설치/로컬 SQLite 에서도 코어 기능은 동작하도록 가드.
try:
    from pgvector.sqlalchemy import Vector
    HAS_PGVECTOR = True
except ImportError:  # pragma: no cover
    HAS_PGVECTOR = False

# 임베딩: Google Gemini(gemini-embedding-001).
# 1536차원 = 3072 동급 품질(MTEB 68.17) + pgvector HNSW 인덱스 한계(2000) 이내.
EMBED_MODEL_NAME = "gemini-embedding-001"
EMBED_DIM = 1536

# ---------------------------------------------------------------------------
# Database URL
# ---------------------------------------------------------------------------
# 저장소 루트 .env 로드 → DATABASE_URL 등. (셸/Railway 실제 환경값이 우선: override=False)
# 컨테이너엔 .env 가 없어(.dockerignore) no-op → Railway 주입 env 가 그대로 쓰임.
load_dotenv(pathlib.Path(__file__).resolve().parent.parent.parent / ".env")

_DEFAULT_SQLITE = pathlib.Path(__file__).resolve().parent.parent / "sqld_learning.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{_DEFAULT_SQLITE}")

# Railway/Heroku 가 주는 'postgres://' → SQLAlchemy 2.0 표준 'postgresql://'
# (드라이버 미지정 시 기본 다이얼렉트는 psycopg2 → requirements_api.txt 의 psycopg2-binary 사용)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

_is_sqlite = DATABASE_URL.startswith("sqlite")

# SQLite: check_same_thread (SQLite 전용). Postgres: TCP keepalive 로 Railway 프록시
# 연결이 다수 왕복/유휴 중 끊기는 'SSL unexpected eof' 를 완화.
if _is_sqlite:
    _connect_args = {"check_same_thread": False}
else:
    _connect_args = {
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
        "sslmode": "require",
    }

engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    # 유휴 커넥션이 끊기는 환경(Railway 등) 대비 → 죽은 커넥션 사전 감지
    pool_pre_ping=not _is_sqlite,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    user_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False, index=True)
    username = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
        nullable=True,
    )
    is_active = Column(Boolean, nullable=False, default=True)


class Question(Base):
    """문제 마스터.

    원본 JSON(json_parser.parse_all) + features.add_features() 결과 19컬럼 + choices 를 그대로 보관.
    runtime 에서는 state.py 가 이 테이블을 통째로 읽어 questions_df(DataFrame)로 만든다.
    PK 형식: f"{subject_id}_{chapter_id}_{question_number}"  (예: "1_1_1")
    """

    __tablename__ = "questions"

    question_id = Column(String, primary_key=True)

    subject_id = Column(Integer, nullable=False, index=True)
    chapter_id = Column(Integer, nullable=False, index=True)
    chapter_name = Column(String, nullable=False, default="")
    question_number = Column(Integer, nullable=False)

    book_section = Column(String, default="")
    book_question_number = Column(Integer, nullable=True)

    question_type = Column(String, index=True, default="")
    question_text = Column(Text, default="")
    sql_code = Column(Text, default="")
    has_sql_asset = Column(Boolean, default=False)

    choice_count = Column(Integer, default=0)
    choice_kinds = Column(String, default="")   # 콤마 구분 (예: "text,sql_query")
    choices = Column(JSON, nullable=True)        # [{"number": 1, "text": "..."}, ...]
    correct_choice = Column(Integer, nullable=True)

    explanation = Column(Text, default="")

    # features.add_features() 산출 → predict / recommend 가 사용
    question_type_encoded = Column(Integer, default=-1)
    choice_kind_complexity = Column(Integer, default=0)
    difficulty = Column(Integer, default=0, index=True)
    difficulty_label = Column(String, default="", index=True)

    # --- provenance: 생성/기존 구분 + 재활용 플라이휠 ---
    # source: 원본 문제집(JSON) = "original" / LLM 생성 = "generated"
    source = Column(String, nullable=False, default="original", index=True)
    # status: 서빙 게이트. 원본은 active, 생성 문제는 검수 전 pending → 승인 시 active
    status = Column(String, nullable=False, default="active", index=True)
    # generated_from: 생성의 근거가 된 부모(원본) question_id (원본이면 NULL)
    generated_from = Column(String, nullable=True, index=True)
    # fitness_score: 생성 문제 적합도 평가 점수 (원본이면 NULL)
    fitness_score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # --- v4 스키마: 원본 자산 보존 + 시험지 과목 + 임베딩 동기화 ---
    # assets: 원본 asset 배열(text_block/data_table/sql_query/erd) 무손실 보존(single source of truth).
    #         question_text/sql_code/has_sql_asset 등 파생 컬럼은 여기서 생성된다.
    assets = Column(JSON, nullable=True)
    # exam_subject: 원본 시험지 과목(기출 M55~M60 만 값). 주제 기반 재분류로 subject_id 와 교차하는 3건 대응.
    exam_subject = Column(SmallInteger, nullable=True)
    # content_hash: md5(question_text + sql_code + explanation). 내용 변경 시 재임베딩/재계산 대상 식별.
    content_hash = Column(String, nullable=False, default="")
    updated_at = Column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('active','pending','rejected','retired')", name="ck_q_status"
        ),
        CheckConstraint("source IN ('original','generated')", name="ck_q_source"),
        # 생성 문제 ↔ 부모 존재 쌍조건: generated 이면 generated_from 필수, 아니면 NULL
        CheckConstraint(
            "(source = 'generated') = (generated_from IS NOT NULL)", name="ck_q_origin"
        ),
        # 기출 중복 적재 방지: 같은 회차·번호가 두 챕터에 들어가는 사고 차단 (Postgres 부분 유니크)
        Index(
            "ux_q_exam",
            "book_section",
            "book_question_number",
            unique=True,
            postgresql_where=text("book_section LIKE 'M%'"),
        ),
    )


class AnswerLog(Base):
    __tablename__ = "answer_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        String,
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # 문제 마스터가 DB에 생겼으므로 FK로 정합성 보장
    # (주의: FK 때문에 적재 순서는 questions 먼저, answer_logs 나중)
    question_id = Column(
        String, ForeignKey("questions.question_id"), nullable=False, index=True
    )
    is_correct = Column(Boolean, nullable=False)
    solve_time_sec = Column(Float, nullable=True)
    logged_at = Column(DateTime, default=datetime.datetime.utcnow)


class QuestionDedupLog(Base):
    """중복 처리 이력 — v3 canonical_id(논리 통합) 대체.

    하드 삭제로 사라진 두 기능을 떠받친다:
      ① 모의고사 복원 시 삭제 슬롯을 kept 문항으로 대체 출제
      ② 플라이휠 dedup 게이트의 폐기 감사 이력
    removed_question_id 는 이미 삭제(또는 retired)된 문항이라 questions FK 를 걸지 않는다.
    """

    __tablename__ = "question_dedup_log"

    removed_question_id = Column(String, primary_key=True)
    kept_question_id = Column(
        String, ForeignKey("questions.question_id"), nullable=False
    )
    # 복원용 스냅샷 (행이 사라지므로 출처 메타를 여기 보존)
    book_section = Column(String, nullable=True)
    book_question_number = Column(Integer, nullable=True)
    exam_subject = Column(SmallInteger, nullable=True)
    removed_assets = Column(JSON, nullable=True)
    # 판정 근거
    similarity = Column(Float, nullable=True)
    method = Column(String, nullable=False, default="manual")  # manual / flywheel_gate
    removed_at = Column(DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (
        CheckConstraint(
            "removed_question_id <> kept_question_id", name="ck_dedup_distinct"
        ),
        Index("ix_dedup_exam", "book_section", "book_question_number"),
        Index("ix_dedup_kept", "kept_question_id"),
    )


class QuestionSimilar(Base):
    """유사도 사전 매핑 — /explain 무쿼리화 + 추천 쿨다운 + 플라이휠 dedup 사전 필터.

    이웃 풀은 serving(status='active')만. refresh_similarities.py 가 풀 리프레시로 채운다.
    PK=(question_id, similar_question_id) — 관계가 곧 키. 중복 이웃을 스키마 차원에서 차단하고,
    순위는 similarity DESC 정렬로 도출(rank 컬럼 폐지). 모델 교체는 model_name 으로 추적.
    """

    __tablename__ = "question_similar"

    question_id = Column(
        String,
        ForeignKey("questions.question_id", ondelete="CASCADE"),
        primary_key=True,
    )
    similar_question_id = Column(
        String,
        ForeignKey("questions.question_id", ondelete="CASCADE"),
        primary_key=True,
    )
    similarity = Column(Float, nullable=False)
    model_name = Column(String, nullable=False)
    computed_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)

    __table_args__ = (
        CheckConstraint(
            "similarity > 0 AND similarity <= 1", name="ck_qsim_similarity"
        ),
        CheckConstraint(
            "question_id <> similar_question_id", name="ck_qsim_distinct"
        ),
        Index("ix_qsim_reverse", "similar_question_id"),
    )


if HAS_PGVECTOR:

    class QuestionEmbedding(Base):
        """문제 임베딩(pgvector). questions 와 1:1, Postgres 전용.

        신규 생성 문제도 여기에 적재되면 즉시 유사도 검색 대상이 된다(인덱스 재빌드 불필요).
        HNSW(cosine) 인덱스는 vectorize_questions.py 에서 별도 생성.
        """

        __tablename__ = "question_embeddings"

        question_id = Column(
            String,
            ForeignKey("questions.question_id", ondelete="CASCADE"),
            primary_key=True,
        )
        embedding = Column(Vector(EMBED_DIM), nullable=False)
        model_name = Column(String, nullable=False, default=EMBED_MODEL_NAME)
        # content_hash: 임베딩 생성 시점의 questions.content_hash. 스테일(문항 수정·모델 교체) 검출용.
        content_hash = Column(String, nullable=False, default="")
        updated_at = Column(
            DateTime,
            default=datetime.datetime.utcnow,
            onupdate=datetime.datetime.utcnow,
        )

else:  # pgvector 미설치 → 벡터 기능 비활성(코어 기능은 정상 동작)
    QuestionEmbedding = None


def ensure_vector_extension() -> bool:
    """Postgres + pgvector 일 때 'CREATE EXTENSION vector'. 사용 가능 여부를 반환.

    - 로컬 SQLite / pgvector 미설치 → False (코어 테이블만 생성)
    - base Postgres(확장 미존재) → 생성 실패 시 False 로 안전하게 강등
    """
    if _is_sqlite or not HAS_PGVECTOR:
        return False
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[DB] pgvector 확장 활성화 실패 → 벡터 테이블 생략: {e}", flush=True)
        return False


def create_views() -> None:
    """serving_questions 뷰 — 추천·연습·RAG 컨텍스트 공통 서빙 풀(status='active').

    CREATE OR REPLACE 는 SQLite 미지원이라 DROP+CREATE 로 통일(양 DB 호환·멱등).
    """
    with engine.begin() as conn:
        conn.execute(text("DROP VIEW IF EXISTS serving_questions"))
        conn.execute(
            text(
                "CREATE VIEW serving_questions AS "
                "SELECT * FROM questions WHERE status = 'active'"
            )
        )


def create_tables() -> None:
    # FK 의존성에 따라 questions → answer_logs 순서로 알아서 생성됨
    vector_ok = ensure_vector_extension()
    if QuestionEmbedding is not None and vector_ok:
        Base.metadata.create_all(bind=engine)  # 코어 + question_embeddings
    else:
        # 벡터 미지원 환경 → 벡터 의존 테이블(question_embeddings)만 생략, 나머지 코어 전부 생성
        core = [
            User.__table__,
            Question.__table__,
            AnswerLog.__table__,
            QuestionDedupLog.__table__,
            QuestionSimilar.__table__,
        ]
        Base.metadata.create_all(bind=engine, tables=core)
    create_views()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
