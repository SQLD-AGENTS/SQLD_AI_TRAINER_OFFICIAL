"""add_social_login_columns

Revision ID: c5d2e3f4a6b7
Revises: b3f1a2c9d4e5
Create Date: 2026-06-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c5d2e3f4a6b7'
down_revision: Union[str, Sequence[str], None] = 'b3f1a2c9d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('social_provider', sa.String(32), nullable=True))
    op.add_column('users', sa.Column('social_id', sa.String(256), nullable=True))
    op.alter_column('users', 'hashed_password', nullable=True)


def downgrade() -> None:
    op.execute("UPDATE users SET hashed_password = '' WHERE hashed_password IS NULL")
    op.alter_column('users', 'hashed_password', nullable=False)
    op.drop_column('users', 'social_id')
    op.drop_column('users', 'social_provider')
