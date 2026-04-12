"""add user preference model for personalization

Revision ID: 0004_user_preferences
Revises: 0003_artifact_chat_linkage
Create Date: 2026-04-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0004_user_preferences"
down_revision = "0003_artifact_chat_linkage"
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
    if "user_preferences" not in tables:
        op.create_table(
            "user_preferences",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("schema_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("default_depth", sa.String(length=16), nullable=False, server_default=sa.text("'brief'")),
            sa.Column("tone", sa.String(length=16), nullable=False, server_default=sa.text("'neutral'")),
            sa.Column("strictness_preference", sa.String(length=16), nullable=False, server_default=sa.text("'balanced'")),
            sa.Column("schedule_preference", sa.String(length=16), nullable=False, server_default=sa.text("'flexible'")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("user_id", name="uq_user_preferences_user_id"),
        )
    else:
        columns = _get_column_names("user_preferences")
        if "schema_version" not in columns:
            op.add_column(
                "user_preferences",
                sa.Column("schema_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
            )
        if "default_depth" not in columns:
            op.add_column(
                "user_preferences",
                sa.Column("default_depth", sa.String(length=16), nullable=False, server_default=sa.text("'brief'")),
            )
        if "tone" not in columns:
            op.add_column(
                "user_preferences",
                sa.Column("tone", sa.String(length=16), nullable=False, server_default=sa.text("'neutral'")),
            )
        if "strictness_preference" not in columns:
            op.add_column(
                "user_preferences",
                sa.Column("strictness_preference", sa.String(length=16), nullable=False, server_default=sa.text("'balanced'")),
            )
        if "schedule_preference" not in columns:
            op.add_column(
                "user_preferences",
                sa.Column("schedule_preference", sa.String(length=16), nullable=False, server_default=sa.text("'flexible'")),
            )
        if "created_at" not in columns:
            op.add_column(
                "user_preferences",
                sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            )
        if "updated_at" not in columns:
            op.add_column(
                "user_preferences",
                sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            )

    indexes = _get_index_names("user_preferences")
    if "ix_user_preferences_user_id" not in indexes:
        op.create_index("ix_user_preferences_user_id", "user_preferences", ["user_id"], unique=True)
    if "ix_user_preferences_updated_at" not in indexes:
        op.create_index("ix_user_preferences_updated_at", "user_preferences", ["updated_at"], unique=False)


def downgrade() -> None:
    tables = _get_table_names()
    if "user_preferences" not in tables:
        return

    indexes = _get_index_names("user_preferences")
    if "ix_user_preferences_updated_at" in indexes:
        op.drop_index("ix_user_preferences_updated_at", table_name="user_preferences")
    if "ix_user_preferences_user_id" in indexes:
        op.drop_index("ix_user_preferences_user_id", table_name="user_preferences")

    op.drop_table("user_preferences")

