"""Change coaching_mode default from 'gangbiao' to 'a3'.

Revision ID: 009
Revises: 008
"""

from alembic import op
import sqlalchemy as sa


revision = "009_coaching_mode_default_a3"
down_revision = "008_coaching_mode_column"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Update existing rows: gangbiao → a3
    op.execute("UPDATE chat_sessions SET coaching_mode = 'a3' WHERE coaching_mode = 'gangbiao'")
    # Change the column server_default
    op.alter_column(
        "chat_sessions",
        "coaching_mode",
        server_default=sa.text("'a3'"),
    )


def downgrade() -> None:
    op.execute("UPDATE chat_sessions SET coaching_mode = 'gangbiao' WHERE coaching_mode = 'a3'")
    op.alter_column(
        "chat_sessions",
        "coaching_mode",
        server_default=sa.text("'gangbiao'"),
    )
