"""add provider and provider_user_id to users for SSO

Revision ID: 003_user_sso_fields
Revises: 002_auth_sessions
Create Date: 2026-06-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "003_user_sso_fields"
down_revision: Union[str, Sequence[str], None] = "002_auth_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Make email and password_hash nullable (SSO users may not have them)
    op.alter_column("users", "email", existing_type=sa.String(255), nullable=True)
    op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=True)

    # Add provider column with default 'local' for existing users
    op.add_column(
        "users",
        sa.Column("provider", sa.String(20), server_default=sa.text("'local'"), nullable=False),
    )

    # Add provider_user_id column (CAS employee number)
    op.add_column(
        "users",
        sa.Column("provider_user_id", sa.String(100), nullable=True),
    )

    # Unique index on provider_user_id for SSO lookups
    op.create_index("ix_users_provider_user_id", "users", ["provider_user_id"], unique=True)

    # Composite index for SSO queries: WHERE provider='cas' AND provider_user_id=?
    op.create_index("ix_users_provider_provider_user_id", "users", ["provider", "provider_user_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_users_provider_provider_user_id", table_name="users")
    op.drop_index("ix_users_provider_user_id", table_name="users")
    op.drop_column("users", "provider_user_id")
    op.drop_column("users", "provider")
    op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=False)
    op.alter_column("users", "email", existing_type=sa.String(255), nullable=False)
