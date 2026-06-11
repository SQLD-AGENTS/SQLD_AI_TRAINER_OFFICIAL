"""v4 schema (consolidated) — questions 자산/해시 + dedup_log + question_similar

b7d9f2a4c6e8 / c8e0a3b5d7f9 / e5f7a9c1b3d4 / f6a8b0c2d4e6 / a1b2c3d4e5f6 5개를
하나로 합친 스쿼시. 어지러운 v4 진화 이력(뷰 add→drop, 컬럼 패치, top3→관계키 재설계,
브랜치 재배선)을 c5d2e3f4a6b7(인증 마이그레이션 head) 위 단일 최종 상태로 정리한다.

최종 상태(= 현재 Railway 실스키마 + e5f7 누락분 computed_at 보정):
  questions            : +assets(JSON) +exam_subject(smallint) +content_hash(NOT NULL '')
                         +updated_at(timestamp), CHECK ck_q_status/source/origin, ux_q_exam
  question_embeddings  : +content_hash(NOT NULL '')
  question_dedup_log   : slim(removed PK, kept FK, similarity, method, removed_at) + ix_dedup_kept
  question_similar     : PK(question_id, similar_question_id), similarity/model_name,
                         computed_at timestamptz NOT NULL DEFAULT now(), CHECK 2종, ix_qsim_reverse
  serving_questions 뷰 : 없음(미사용 → 폐지)

전부 멱등(IF NOT EXISTS / DO-catch)이라 fresh 배포·기존 Railway 양쪽에서 안전.
base 테이블(questions/question_embeddings)은 create_tables(metadata.create_all) 가 만든다는
기존 하이브리드 전제를 따른다 — 본 마이그레이션은 v4 델타만 멱등 적용.

Revision ID: d4e5f6a7b8c9
Revises: c5d2e3f4a6b7
Create Date: 2026-06-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c5d2e3f4a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # === questions: v4 컬럼 ===
    op.execute("ALTER TABLE questions ADD COLUMN IF NOT EXISTS assets JSON")
    op.execute("ALTER TABLE questions ADD COLUMN IF NOT EXISTS exam_subject SMALLINT")
    op.execute(
        "ALTER TABLE questions "
        "ADD COLUMN IF NOT EXISTS content_hash VARCHAR NOT NULL DEFAULT ''"
    )
    op.execute("ALTER TABLE questions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP")

    # === questions: CHECK 제약 ===
    op.execute(
        "DO $$ BEGIN ALTER TABLE questions ADD CONSTRAINT ck_q_status "
        "CHECK (status IN ('active','pending','rejected','retired')); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )
    op.execute(
        "DO $$ BEGIN ALTER TABLE questions ADD CONSTRAINT ck_q_source "
        "CHECK (source IN ('original','generated')); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )
    op.execute(
        "DO $$ BEGIN ALTER TABLE questions ADD CONSTRAINT ck_q_origin "
        "CHECK ((source = 'generated') = (generated_from IS NOT NULL)); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )

    # === questions: 기출 중복 방지 부분 유니크 ===
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_q_exam "
        "ON questions (book_section, book_question_number) "
        "WHERE book_section LIKE 'M%'"
    )

    # === question_embeddings: content_hash ===
    op.execute(
        "ALTER TABLE question_embeddings "
        "ADD COLUMN IF NOT EXISTS content_hash VARCHAR NOT NULL DEFAULT ''"
    )

    # === question_dedup_log (slim) ===
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS question_dedup_log (
            removed_question_id VARCHAR NOT NULL,
            kept_question_id    VARCHAR NOT NULL,
            similarity          DOUBLE PRECISION,
            method              VARCHAR NOT NULL DEFAULT 'manual',
            removed_at          TIMESTAMP,
            CONSTRAINT question_dedup_log_pkey PRIMARY KEY (removed_question_id),
            CONSTRAINT question_dedup_log_kept_question_id_fkey
                FOREIGN KEY (kept_question_id) REFERENCES questions(question_id),
            CONSTRAINT ck_dedup_distinct
                CHECK (removed_question_id <> kept_question_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_dedup_kept "
        "ON question_dedup_log (kept_question_id)"
    )

    # === question_similar (관계키 모델, 최종) ===
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS question_similar (
            question_id         VARCHAR NOT NULL,
            similar_question_id VARCHAR NOT NULL,
            similarity          DOUBLE PRECISION NOT NULL,
            model_name          VARCHAR NOT NULL,
            computed_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT question_similar_pkey
                PRIMARY KEY (question_id, similar_question_id),
            CONSTRAINT question_similar_question_id_fkey
                FOREIGN KEY (question_id) REFERENCES questions(question_id)
                ON DELETE CASCADE,
            CONSTRAINT question_similar_similar_question_id_fkey
                FOREIGN KEY (similar_question_id) REFERENCES questions(question_id)
                ON DELETE CASCADE,
            CONSTRAINT ck_qsim_similarity
                CHECK (similarity > 0 AND similarity <= 1),
            CONSTRAINT ck_qsim_distinct
                CHECK (question_id <> similar_question_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_qsim_reverse "
        "ON question_similar (similar_question_id)"
    )

    # === question_similar.computed_at 보정 (e5f7 누락분 — 기존 nullable 테이블 복구) ===
    # 기존 Railway 테이블은 nullable·default 없음 상태라 raw INSERT 시 NULL 유입 위험 →
    # server_default=now() + NOT NULL 로 DB 레벨 차단(스테일 검사 V4 정합).
    op.execute("ALTER TABLE question_similar ALTER COLUMN computed_at SET DEFAULT now()")
    op.execute("UPDATE question_similar SET computed_at = now() WHERE computed_at IS NULL")
    op.execute("ALTER TABLE question_similar ALTER COLUMN computed_at SET NOT NULL")


def downgrade() -> None:
    # v4 델타 역적용 → c5d2e3f4a6b7 상태로 복귀
    op.execute("DROP TABLE IF EXISTS question_similar")
    op.execute("DROP TABLE IF EXISTS question_dedup_log")
    op.execute("ALTER TABLE question_embeddings DROP COLUMN IF EXISTS content_hash")
    op.execute("DROP INDEX IF EXISTS ux_q_exam")
    op.execute("ALTER TABLE questions DROP CONSTRAINT IF EXISTS ck_q_origin")
    op.execute("ALTER TABLE questions DROP CONSTRAINT IF EXISTS ck_q_source")
    op.execute("ALTER TABLE questions DROP CONSTRAINT IF EXISTS ck_q_status")
    op.execute("ALTER TABLE questions DROP COLUMN IF EXISTS updated_at")
    op.execute("ALTER TABLE questions DROP COLUMN IF EXISTS content_hash")
    op.execute("ALTER TABLE questions DROP COLUMN IF EXISTS exam_subject")
    op.execute("ALTER TABLE questions DROP COLUMN IF EXISTS assets")
