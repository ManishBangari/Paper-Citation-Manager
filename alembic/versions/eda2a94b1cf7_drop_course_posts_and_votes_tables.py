"""drop course posts and votes tables

Revision ID: eda2a94b1cf7
Revises: 260707c86524
Create Date: 2026-10-05 05:58:08.245915

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'eda2a94b1cf7'
down_revision: Union[str, Sequence[str], None] = '260707c86524'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove the tables left over from the FastAPI course project (posts and votes)."""
    # votes points at posts, so it has to go first
    op.drop_table('votes')
    op.drop_table('posts')


def downgrade() -> None:
    """Recreate the empty course tables (their rows are not restored)."""
    op.create_table('posts',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('title', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('content', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('owner_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('published', sa.BOOLEAN(), server_default=sa.text('true'), autoincrement=False, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('posts_users_fk'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('posts_pkey'))
    )
    op.create_table('votes',
    sa.Column('user_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('post_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['post_id'], ['posts.id'], name=op.f('votes_post_id_fkey'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('votes_user_id_fkey'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'post_id', name=op.f('votes_pkey'))
    )
