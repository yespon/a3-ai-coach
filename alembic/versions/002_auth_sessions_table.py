"""auth_sessions table for CAS SSO

Revision ID: 002_auth_sessions
Revises: 001_initial
Create Date: 2026-06-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID


# revision identifiers, used by Alembic.
revision: str = "002_auth_sessions"
down_revision: Union[str, Sequence[str], None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "auth_sessions",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("session_token", sa.String(64), unique=True, nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cas_ticket", sa.String(255), nullable=True),
        sa.Column("created_at", TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.Column("last_seen_at", TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.Column("expires_at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("revoked_at", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip", sa.String(45), nullable=True),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_cas_ticket", "auth_sessions", ["cas_ticket"])
    op.create_index("ix_auth_sessions_expires", "auth_sessions", ["expires_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_auth_sessions_expires", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_cas_ticket", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
