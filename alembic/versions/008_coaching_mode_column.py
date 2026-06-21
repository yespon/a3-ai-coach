"""Add coaching_mode column to chat_sessions.

Revision ID: 008
Revises: 007
"""

from alembic import op
import sqlalchemy as sa


revision = "008_coaching_mode_column"
down_revision = "007_session_title_pin_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column("coaching_mode", sa.String(20), server_default=sa.text("'gangbiao'"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("chat_sessions", "coaching_mode")
