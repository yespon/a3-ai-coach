"""Add title, pinned, deleted_at to chat_sessions.

Revision ID: 007
Revises: 006
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TIMESTAMP


revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chat_sessions", sa.Column("title", sa.String(200), nullable=True))
    op.add_column(
        "chat_sessions",
        sa.Column("pinned", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "chat_sessions",
        sa.Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("chat_sessions", "deleted_at")
    op.drop_column("chat_sessions", "pinned")
    op.drop_column("chat_sessions", "title")
