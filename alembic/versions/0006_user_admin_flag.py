"""add admin flag to users

Revision ID: 0006_user_admin_flag
Revises: 0005_premium_analytics_events
Create Date: 2026-04-15
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0006_user_admin_flag"
down_revision = "0005_premium_analytics_events"
branch_labels = None
depends_on = None


def _get_table_names() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return set(inspector.get_table_names())


def _get_column_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {col["name"] for col in inspector.get_columns(table_name)}


def _get_index_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {idx["name"] for idx in inspector.get_indexes(table_name)}


def upgrade() -> None:
    tables = _get_table_names()
    if "users" not in tables:
        return

    columns = _get_column_names("users")
    if "is_admin" not in columns:
        op.add_column(
            "users",
            sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )

    indexes = _get_index_names("users")
    if "ix_users_is_admin" not in indexes:
        op.create_index("ix_users_is_admin", "users", ["is_admin"], unique=False)


def downgrade() -> None:
    tables = _get_table_names()
    if "users" not in tables:
        return

    indexes = _get_index_names("users")
    if "ix_users_is_admin" in indexes:
        op.drop_index("ix_users_is_admin", table_name="users")

    columns = _get_column_names("users")
    if "is_admin" in columns:
        with op.batch_alter_table("users") as batch_op:
            batch_op.drop_column("is_admin")

