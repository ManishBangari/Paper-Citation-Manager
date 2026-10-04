"""add last few columns to posts table

Revision ID: bed82c1e381d
Revises: f8e647522f0c
Create Date: 2026-09-13 17:06:24.526909

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bed82c1e381d'
down_revision: Union[str, Sequence[str], None] = 'f8e647522f0c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("posts", sa.Column("published", sa.Boolean, nullable=False, server_default='TRUE'))
    op.add_column("posts", sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')))
    pass


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("posts", "published")
    op.drop_column("posts", "created_at")
    pass
