"""finalize schema: redesign question_similar + slim question_dedup_log

확정 스키마(스키마 구조 변경.md / 테이블별 설계근거서) 반영:

[1] question_similar 재설계 (top3 → 관계-키 모델)
- 테이블명 question_similar_top3 → question_similar
- PK (question_id, rank) → (question_id, similar_question_id) : 중복 이웃을 키로 차단,
  순위는 similarity DESC 정렬로 도출(rank 컬럼 폐지)
- similarity CHECK (0 초과 1 이하) 추가, ck_qsim_rank 제거
- computed_at → timestamptz

[2] question_dedup_log 축소 (모의고사 복원 기능 폐지)
- 복원 스냅샷 4컬럼 제거: book_section, book_question_number, exam_subject,
  removed_assets (+ ix_dedup_exam) → 순수 감사·캘리브레이션 테이블
- 잔존: removed_question_id(PK), kept_question_id(FK), similarity, method, removed_at

두 테이블 모두 아직 미적재(Phase 1/2 미실행)이므로 데이터 손실 없음.

Revision ID: c8e0a3b5d7f9
Revises: b7d9f2a4c6e8
Create Date: 2026-06-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c8e0a3b5d7f9"
down_revision: Union[str, Sequence[str], None] = "b7d9f2a4c6e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # [1] question_similar: 기존 top3(미적재) 제거 후 관계-키 모델로 재생성
    op.drop_index("ix_qsim_reverse", table_name="question_similar_top3")
    op.drop_table("question_similar_top3")

    op.create_table(
        "question_similar",
        sa.Column("question_id", sa.String(), nullable=False),
        sa.Column("similar_question_id", sa.String(), nullable=False),
        sa.Column("similarity", sa.Float(), nullable=False),
        sa.Column("model_name", sa.String(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("question_id", "similar_question_id"),
        sa.ForeignKeyConstraint(
            ["question_id"], ["questions.question_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["similar_question_id"], ["questions.question_id"], ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "similarity > 0 AND similarity <= 1", name="ck_qsim_similarity"
        ),
        sa.CheckConstraint(
            "question_id <> similar_question_id", name="ck_qsim_distinct"
        ),
    )
    op.create_index("ix_qsim_reverse", "question_similar", ["similar_question_id"])

    # [2] question_dedup_log: 복원 스냅샷 4컬럼 제거 → 순수 감사·캘리브레이션
    op.drop_index("ix_dedup_exam", table_name="question_dedup_log")
    op.drop_column("question_dedup_log", "removed_assets")
    op.drop_column("question_dedup_log", "exam_subject")
    op.drop_column("question_dedup_log", "book_question_number")
    op.drop_column("question_dedup_log", "book_section")


def downgrade() -> None:
    """Downgrade schema."""
    # [2] question_dedup_log: 복원 스냅샷 4컬럼 복원
    op.add_column(
        "question_dedup_log", sa.Column("book_section", sa.String(), nullable=True)
    )
    op.add_column(
        "question_dedup_log",
        sa.Column("book_question_number", sa.Integer(), nullable=True),
    )
    op.add_column(
        "question_dedup_log",
        sa.Column("exam_subject", sa.SmallInteger(), nullable=True),
    )
    op.add_column(
        "question_dedup_log", sa.Column("removed_assets", sa.JSON(), nullable=True)
    )
    op.create_index(
        "ix_dedup_exam", "question_dedup_log", ["book_section", "book_question_number"]
    )

    # [1] question_similar → top3 복원
    op.drop_index("ix_qsim_reverse", table_name="question_similar")
    op.drop_table("question_similar")

    op.create_table(
        "question_similar_top3",
        sa.Column("question_id", sa.String(), nullable=False),
        sa.Column("rank", sa.SmallInteger(), nullable=False),
        sa.Column("similar_question_id", sa.String(), nullable=False),
        sa.Column("similarity", sa.Float(), nullable=False),
        sa.Column("model_name", sa.String(), nullable=False),
        sa.Column("computed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("question_id", "rank"),
        sa.ForeignKeyConstraint(
            ["question_id"], ["questions.question_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["similar_question_id"], ["questions.question_id"], ondelete="CASCADE"
        ),
        sa.CheckConstraint("rank BETWEEN 1 AND 3", name="ck_qsim_rank"),
        sa.CheckConstraint(
            "question_id <> similar_question_id", name="ck_qsim_distinct"
        ),
    )
    op.create_index(
        "ix_qsim_reverse", "question_similar_top3", ["similar_question_id"]
    )
