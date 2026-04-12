"""add conversation linkage columns to artifacts

Revision ID: 0003_artifact_chat_linkage
Revises: 0002_artifact_metadata
Create Date: 2026-04-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0003_artifact_chat_linkage"
down_revision = "0002_artifact_metadata"
branch_labels = None
depends_on = None


def _get_column_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {col["name"] for col in inspector.get_columns(table_name)}


def _get_index_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {idx["name"] for idx in inspector.get_indexes(table_name)}


def upgrade() -> None:
    columns = _get_column_names("artifacts")
    if "conversation_session_id" not in columns:
        op.add_column(
            "artifacts",
            sa.Column("conversation_session_id", sa.String(length=128), nullable=True),
        )
    if "conversation_turn_ref" not in columns:
        op.add_column(
            "artifacts",
            sa.Column("conversation_turn_ref", sa.String(length=64), nullable=True),
        )

    indexes = _get_index_names("artifacts")
    if "ix_artifact_user_conversation" not in indexes:
        op.create_index(
            "ix_artifact_user_conversation",
            "artifacts",
            ["user_id", "conversation_session_id"],
            unique=False,
        )


def downgrade() -> None:
    indexes = _get_index_names("artifacts")
    if "ix_artifact_user_conversation" in indexes:
        op.drop_index("ix_artifact_user_conversation", table_name="artifacts")

    columns = _get_column_names("artifacts")
    if "conversation_turn_ref" in columns:
        op.drop_column("artifacts", "conversation_turn_ref")
    if "conversation_session_id" in columns:
        op.drop_column("artifacts", "conversation_session_id")

