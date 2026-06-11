"""v4 schema: questions.assets/exam_subject/content_hash/updated_at + check/uniq,
question_embeddings.content_hash, question_dedup_log, question_similar_top3, serving_questions view

v4 설계(하드 삭제판)의 additive 스키마 요소. canonical_id 는 도입하지 않음(애초 부재).
운영 Postgres 대상 — question_embeddings(pgvector) 존재 가정. 로컬 SQLite 는
create_tables(metadata.create_all)가 신규 스키마를 직접 생성하므로 본 마이그레이션 불필요.

Revision ID: b7d9f2a4c6e8
Revises: e17815e1e77e
Create Date: 2026-06-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7d9f2a4c6e8"
down_revision: Union[str, Sequence[str], None] = "e17815e1e77e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # --- questions: v4 컬럼 ---
    op.add_column("questions", sa.Column("assets", sa.JSON(), nullable=True))
    op.add_column("questions", sa.Column("exam_subject", sa.SmallInteger(), nullable=True))
    # content_hash: 기존 행은 '' 로 backfill(server_default), 이후 파이프라인이 채움
    op.add_column(
        "questions",
        sa.Column("content_hash", sa.String(), nullable=False, server_default=""),
    )
    op.add_column("questions", sa.Column("updated_at", sa.DateTime(), nullable=True))

    # --- questions: CHECK 제약 (기존 데이터 source='original'/generated_from NULL → 충족) ---
    op.create_check_constraint(
        "ck_q_status", "questions",
        "status IN ('active','pending','rejected','retired')",
    )
    op.create_check_constraint(
        "ck_q_source", "questions", "source IN ('original','generated')",
    )
    op.create_check_constraint(
        "ck_q_origin", "questions",
        "(source = 'generated') = (generated_from IS NOT NULL)",
    )

    # --- 기출 중복 적재 방지 (부분 유니크) ---
    op.create_index(
        "ux_q_exam", "questions", ["book_section", "book_question_number"],
        unique=True, postgresql_where=sa.text("book_section LIKE 'M%'"),
    )

    # --- question_embeddings: content_hash (pgvector 환경 = 운영 Postgres) ---
    op.add_column(
        "question_embeddings",
        sa.Column("content_hash", sa.String(), nullable=False, server_default=""),
    )

    # --- question_dedup_log (canonical 대체) ---
    op.create_table(
        "question_dedup_log",
        sa.Column("removed_question_id", sa.String(), nullable=False),
        sa.Column("kept_question_id", sa.String(), nullable=False),
        sa.Column("book_section", sa.String(), nullable=True),
        sa.Column("book_question_number", sa.Integer(), nullable=True),
        sa.Column("exam_subject", sa.SmallInteger(), nullable=True),
        sa.Column("removed_assets", sa.JSON(), nullable=True),
        sa.Column("similarity", sa.Float(), nullable=True),
        sa.Column("method", sa.String(), nullable=False, server_default="manual"),
        sa.Column("removed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("removed_question_id"),
        sa.ForeignKeyConstraint(["kept_question_id"], ["questions.question_id"]),
        sa.CheckConstraint(
            "removed_question_id <> kept_question_id", name="ck_dedup_distinct"
        ),
    )
    op.create_index(
        "ix_dedup_exam", "question_dedup_log", ["book_section", "book_question_number"]
    )
    op.create_index("ix_dedup_kept", "question_dedup_log", ["kept_question_id"])

    # --- question_similar_top3 (유사도 사전 매핑) ---
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

    # --- serving_questions 뷰 ---
    op.execute("DROP VIEW IF EXISTS serving_questions")
    op.execute(
        "CREATE VIEW serving_questions AS "
        "SELECT * FROM questions WHERE status = 'active'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP VIEW IF EXISTS serving_questions")

    op.drop_index("ix_qsim_reverse", table_name="question_similar_top3")
    op.drop_table("question_similar_top3")

    op.drop_index("ix_dedup_kept", table_name="question_dedup_log")
    op.drop_index("ix_dedup_exam", table_name="question_dedup_log")
    op.drop_table("question_dedup_log")

    op.drop_column("question_embeddings", "content_hash")

    op.drop_index("ux_q_exam", table_name="questions")
    op.drop_constraint("ck_q_origin", "questions", type_="check")
    op.drop_constraint("ck_q_source", "questions", type_="check")
    op.drop_constraint("ck_q_status", "questions", type_="check")
    op.drop_column("questions", "updated_at")
    op.drop_column("questions", "content_hash")
    op.drop_column("questions", "exam_subject")
    op.drop_column("questions", "assets")
