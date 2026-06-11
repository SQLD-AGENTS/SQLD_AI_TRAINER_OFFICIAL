"""add_avatar_url_token_version_username_unique

Revision ID: b3f1a2c9d4e5
Revises: e17815e1e77e
Create Date: 2026-06-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b3f1a2c9d4e5'
down_revision: Union[str, Sequence[str], None] = 'e17815e1e77e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('avatar_url', sa.String(), nullable=True))
    op.add_column('users', sa.Column('token_version', sa.Integer(), nullable=True))
    op.execute("UPDATE users SET token_version = 0 WHERE token_version IS NULL")
    op.alter_column('users', 'token_version', nullable=False)
    op.create_unique_constraint('uq_users_username', 'users', ['username'])


def downgrade() -> None:
    op.drop_constraint('uq_users_username', 'users', type_='unique')
    op.drop_column('users', 'token_version')
    op.drop_column('users', 'avatar_url')
