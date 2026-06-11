"""add_user_updated_at_is_active_and_answerlog_user_fk

Revision ID: e17815e1e77e
Revises: 
Create Date: 2026-06-09 09:54:51.421321

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e17815e1e77e'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # answer_logs.user_id: NOT NULL → nullable + FK → users.user_id (소프트 삭제 시 SET NULL)
    op.alter_column('answer_logs', 'user_id',
               existing_type=sa.VARCHAR(),
               nullable=True)
    op.create_foreign_key(
        'fk_answer_logs_user_id', 'answer_logs', 'users',
        ['user_id'], ['user_id'], ondelete='SET NULL',
    )
    # users: updated_at, is_active 컬럼 추가
    # is_active: 기존 행을 true 로 backfill 한 뒤 NOT NULL 제약 추가
    op.add_column('users', sa.Column('updated_at', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('is_active', sa.Boolean(), nullable=True))
    op.execute("UPDATE users SET is_active = TRUE WHERE is_active IS NULL")
    op.alter_column('users', 'is_active', nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'is_active')
    op.drop_column('users', 'updated_at')
    op.drop_constraint('fk_answer_logs_user_id', 'answer_logs', type_='foreignkey')
    op.alter_column('answer_logs', 'user_id',
               existing_type=sa.VARCHAR(),
               nullable=False)
