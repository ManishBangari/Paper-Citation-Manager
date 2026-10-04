"""add content column to post table

Revision ID: b86bfcf3fc25
Revises: f7886800c4fa
Create Date: 2026-09-13 16:51:37.174789

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b86bfcf3fc25'
down_revision: Union[str, Sequence[str], None] = 'f7886800c4fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("posts", sa.Column("content", sa.String, nullable=False))
    pass


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("posts", "content")
    pass
