"""add_is_pinned_to_chat_sessions

Revision ID: 74fd495e32c2
Revises: e481b923c540
Create Date: 2026-10-22 12:42:22.117898

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '74fd495e32c2'
down_revision: Union[str, Sequence[str], None] = 'e481b923c540'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [col["name"] for col in inspector.get_columns("chat_sessions")]
    with op.batch_alter_table("chat_sessions", schema=None) as batch_op:
        if "is_pinned" not in columns:
            batch_op.add_column(sa.Column("is_pinned", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [col["name"] for col in inspector.get_columns("chat_sessions")]
    with op.batch_alter_table("chat_sessions", schema=None) as batch_op:
        if "is_pinned" in columns:
            batch_op.drop_column("is_pinned")

