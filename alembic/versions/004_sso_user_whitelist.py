"""sso user whitelist

Revision ID: 004_sso_user_whitelist
Revises: 003_user_sso_fields
Create Date: 2026-06-14
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

revision: str = "004_sso_user_whitelist"
down_revision: Union[str, Sequence[str], None] = "003_user_sso_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sso_user_whitelist",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("employee_no", sa.String(100), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("source", sa.String(20), server_default=sa.text("'manual'"), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", TIMESTAMP(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_sso_user_whitelist_employee_no", "sso_user_whitelist", ["employee_no"], unique=True)
    op.create_index("ix_sso_user_whitelist_enabled", "sso_user_whitelist", ["enabled"])


def downgrade() -> None:
    op.drop_index("ix_sso_user_whitelist_enabled", table_name="sso_user_whitelist")
    op.drop_index("ix_sso_user_whitelist_employee_no", table_name="sso_user_whitelist")
    op.drop_table("sso_user_whitelist")
