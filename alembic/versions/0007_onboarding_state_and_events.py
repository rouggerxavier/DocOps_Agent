"""add onboarding state and events tables

Revision ID: 0007_onboarding_state_and_events
Revises: 0006_user_admin_flag
Create Date: 2026-04-24
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0007_onboarding_state_and_events"
down_revision = "0006_user_admin_flag"
branch_labels = None
depends_on = None


def _get_table_names() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return set(inspector.get_table_names())


def _get_index_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {idx["name"] for idx in inspector.get_indexes(table_name)}


def _json_type() -> sa.types.TypeEngine:
    """Use JSONB on Postgres for index-friendly storage; portable JSON elsewhere."""
    return postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def _json_default() -> sa.sql.elements.TextClause:
    return sa.text("'{}'::jsonb")


def upgrade() -> None:
    tables = _get_table_names()

    if "user_onboarding_state" not in tables:
        op.create_table(
            "user_onboarding_state",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, unique=True),
            sa.Column("schema_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("welcome_seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("tour_started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("tour_completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("tour_skipped_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("step_completions", _json_type(), nullable=False, server_default=_json_default()),
            sa.Column("section_skips", _json_type(), nullable=False, server_default=_json_default()),
            sa.Column("last_step_seen", sa.String(length=64), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

    state_indexes = _get_index_names("user_onboarding_state")
    if "ix_user_onboarding_state_user_id" not in state_indexes:
        op.create_index(
            "ix_user_onboarding_state_user_id",
            "user_onboarding_state",
            ["user_id"],
            unique=True,
        )

    if "user_onboarding_events" not in _get_table_names():
        op.create_table(
            "user_onboarding_events",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("event_type", sa.String(length=48), nullable=False),
            sa.Column("step_id", sa.String(length=64), nullable=True),
            sa.Column("section_id", sa.String(length=32), nullable=True),
            sa.Column("metadata", _json_type(), nullable=True),
            sa.Column(
                "occurred_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

    event_indexes = _get_index_names("user_onboarding_events")
    if "ix_user_onboarding_events_user_id" not in event_indexes:
        op.create_index(
            "ix_user_onboarding_events_user_id",
            "user_onboarding_events",
            ["user_id"],
            unique=False,
        )
    if "ix_user_onboarding_events_event_type" not in event_indexes:
        op.create_index(
            "ix_user_onboarding_events_event_type",
            "user_onboarding_events",
            ["event_type"],
            unique=False,
        )
    if "ix_user_onboarding_events_occurred_at" not in event_indexes:
        op.create_index(
            "ix_user_onboarding_events_occurred_at",
            "user_onboarding_events",
            ["occurred_at"],
            unique=False,
        )
    if "ix_onboarding_events_user_occurred" not in event_indexes:
        op.create_index(
            "ix_onboarding_events_user_occurred",
            "user_onboarding_events",
            ["user_id", "occurred_at"],
            unique=False,
        )
    if "ix_onboarding_events_event_occurred" not in event_indexes:
        op.create_index(
            "ix_onboarding_events_event_occurred",
            "user_onboarding_events",
            ["event_type", "occurred_at"],
            unique=False,
        )


def downgrade() -> None:
    tables = _get_table_names()

    if "user_onboarding_events" in tables:
        indexes = _get_index_names("user_onboarding_events")
        for name in (
            "ix_onboarding_events_event_occurred",
            "ix_onboarding_events_user_occurred",
            "ix_user_onboarding_events_occurred_at",
            "ix_user_onboarding_events_event_type",
            "ix_user_onboarding_events_user_id",
        ):
            if name in indexes:
                op.drop_index(name, table_name="user_onboarding_events")
        op.drop_table("user_onboarding_events")

    if "user_onboarding_state" in tables:
        indexes = _get_index_names("user_onboarding_state")
        if "ix_user_onboarding_state_user_id" in indexes:
            op.drop_index("ix_user_onboarding_state_user_id", table_name="user_onboarding_state")
        op.drop_table("user_onboarding_state")
