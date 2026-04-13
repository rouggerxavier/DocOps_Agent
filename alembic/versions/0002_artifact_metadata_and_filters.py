"""add artifact metadata columns and indexes for discovery filters

Revision ID: 0002_artifact_metadata
Revises: 0001_baseline
Create Date: 2026-04-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0002_artifact_metadata"
down_revision = "0001_baseline"
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

    if "template_id" not in columns:
        op.add_column("artifacts", sa.Column("template_id", sa.String(length=64), nullable=True))
    if "generation_profile" not in columns:
        op.add_column("artifacts", sa.Column("generation_profile", sa.String(length=64), nullable=True))
    if "confidence_level" not in columns:
        op.add_column("artifacts", sa.Column("confidence_level", sa.String(length=16), nullable=True))
    if "confidence_score" not in columns:
        op.add_column("artifacts", sa.Column("confidence_score", sa.Float(), nullable=True))
    if "metadata_version" not in columns:
        op.add_column(
            "artifacts",
            sa.Column(
                "metadata_version",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("1"),
            ),
        )
    if "source_doc_ids" not in columns:
        op.add_column("artifacts", sa.Column("source_doc_ids", sa.String(length=512), nullable=True))

    indexes = _get_index_names("artifacts")
    if "ix_artifact_user_type" not in indexes:
        op.create_index("ix_artifact_user_type", "artifacts", ["user_id", "artifact_type"], unique=False)
    if "ix_artifact_user_template" not in indexes:
        op.create_index("ix_artifact_user_template", "artifacts", ["user_id", "template_id"], unique=False)
    if "ix_artifact_user_created" not in indexes:
        op.create_index("ix_artifact_user_created", "artifacts", ["user_id", "created_at"], unique=False)
    if "ix_artifact_user_confidence" not in indexes:
        op.create_index("ix_artifact_user_confidence", "artifacts", ["user_id", "confidence_score"], unique=False)


def downgrade() -> None:
    indexes = _get_index_names("artifacts")
    if "ix_artifact_user_confidence" in indexes:
        op.drop_index("ix_artifact_user_confidence", table_name="artifacts")
    if "ix_artifact_user_created" in indexes:
        op.drop_index("ix_artifact_user_created", table_name="artifacts")
    if "ix_artifact_user_template" in indexes:
        op.drop_index("ix_artifact_user_template", table_name="artifacts")
    if "ix_artifact_user_type" in indexes:
        op.drop_index("ix_artifact_user_type", table_name="artifacts")

    columns = _get_column_names("artifacts")
    if "source_doc_ids" in columns:
        op.drop_column("artifacts", "source_doc_ids")
    if "metadata_version" in columns:
        op.drop_column("artifacts", "metadata_version")
    if "confidence_score" in columns:
        op.drop_column("artifacts", "confidence_score")
    if "confidence_level" in columns:
        op.drop_column("artifacts", "confidence_level")
    if "generation_profile" in columns:
        op.drop_column("artifacts", "generation_profile")
    if "template_id" in columns:
        op.drop_column("artifacts", "template_id")

