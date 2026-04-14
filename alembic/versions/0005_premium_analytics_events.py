"""add premium analytics event table

Revision ID: 0005_premium_analytics_events
Revises: 0004_user_preferences
Create Date: 2026-04-14
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0005_premium_analytics_events"
down_revision = "0004_user_preferences"
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
    if "premium_analytics_events" not in tables:
        op.create_table(
            "premium_analytics_events",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("touchpoint", sa.String(length=128), nullable=False),
            sa.Column("capability", sa.String(length=64), nullable=True),
            sa.Column("correlation_id", sa.String(length=128), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
    else:
        columns = _get_column_names("premium_analytics_events")
        if "user_id" not in columns:
            op.add_column(
                "premium_analytics_events",
                sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            )
        if "event_type" not in columns:
            op.add_column("premium_analytics_events", sa.Column("event_type", sa.String(length=64), nullable=False))
        if "touchpoint" not in columns:
            op.add_column("premium_analytics_events", sa.Column("touchpoint", sa.String(length=128), nullable=False))
        if "capability" not in columns:
            op.add_column("premium_analytics_events", sa.Column("capability", sa.String(length=64), nullable=True))
        if "correlation_id" not in columns:
            op.add_column("premium_analytics_events", sa.Column("correlation_id", sa.String(length=128), nullable=True))
        if "metadata_json" not in columns:
            op.add_column("premium_analytics_events", sa.Column("metadata_json", sa.Text(), nullable=True))
        if "created_at" not in columns:
            op.add_column(
                "premium_analytics_events",
                sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            )

    indexes = _get_index_names("premium_analytics_events")
    if "ix_premium_analytics_events_user_id" not in indexes:
        op.create_index("ix_premium_analytics_events_user_id", "premium_analytics_events", ["user_id"], unique=False)
    if "ix_premium_analytics_events_event_type" not in indexes:
        op.create_index("ix_premium_analytics_events_event_type", "premium_analytics_events", ["event_type"], unique=False)
    if "ix_premium_analytics_events_touchpoint" not in indexes:
        op.create_index("ix_premium_analytics_events_touchpoint", "premium_analytics_events", ["touchpoint"], unique=False)
    if "ix_premium_analytics_events_capability" not in indexes:
        op.create_index("ix_premium_analytics_events_capability", "premium_analytics_events", ["capability"], unique=False)
    if "ix_premium_analytics_events_created_at" not in indexes:
        op.create_index("ix_premium_analytics_events_created_at", "premium_analytics_events", ["created_at"], unique=False)
    if "ix_premium_analytics_touchpoint_created" not in indexes:
        op.create_index(
            "ix_premium_analytics_touchpoint_created",
            "premium_analytics_events",
            ["touchpoint", "created_at"],
            unique=False,
        )
    if "ix_premium_analytics_event_created" not in indexes:
        op.create_index(
            "ix_premium_analytics_event_created",
            "premium_analytics_events",
            ["event_type", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    tables = _get_table_names()
    if "premium_analytics_events" not in tables:
        return

    indexes = _get_index_names("premium_analytics_events")
    for name in (
        "ix_premium_analytics_event_created",
        "ix_premium_analytics_touchpoint_created",
        "ix_premium_analytics_events_created_at",
        "ix_premium_analytics_events_capability",
        "ix_premium_analytics_events_touchpoint",
        "ix_premium_analytics_events_event_type",
        "ix_premium_analytics_events_user_id",
    ):
        if name in indexes:
            op.drop_index(name, table_name="premium_analytics_events")

    op.drop_table("premium_analytics_events")
