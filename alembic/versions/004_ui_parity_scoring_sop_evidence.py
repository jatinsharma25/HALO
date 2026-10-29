"""Add incident scoring/disposition, per-zone loitering threshold, SOP table,
and a second (unredacted, role-protected) evidence clip variant.

Revision ID: 004
Revises: 003
Create Date: 2026-09-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable: scores are computed by the correlator when an incident is
    # created/updated, so a row can briefly exist without them, and rows from
    # before this migration genuinely have none.
    op.add_column("incidents", sa.Column("impact_score", sa.Float(), nullable=True))
    op.add_column("incidents", sa.Column("confidence_score", sa.Float(), nullable=True))
    op.add_column("incidents", sa.Column("explanation", sa.Text(), nullable=True))
    # No DB-level CHECK: SQLite can't ALTER-add a constraint without batch
    # table rebuild. Validated at the router layer instead (see incidents/router.py).
    op.add_column("incidents", sa.Column("disposition", sa.String(), nullable=True))

    # Null means "use the global LOITERING_SECONDS default".
    op.add_column("zones", sa.Column("loitering_threshold_s", sa.Integer(), nullable=True))

    # The redacted clip already produced is renamed in intent (not in column)
    # to "preview"; this adds the unredacted original alongside it. Nullable:
    # existing packages predate the original capture and have none.
    op.add_column("evidence_packages", sa.Column("original_clip_path", sa.String(), nullable=True))

    op.create_table(
        "sops",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("incident_type", sa.String(), nullable=False, unique=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("steps_text", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("sops")
    op.drop_column("evidence_packages", "original_clip_path")
    op.drop_column("zones", "loitering_threshold_s")
    op.drop_column("incidents", "disposition")
    op.drop_column("incidents", "explanation")
    op.drop_column("incidents", "confidence_score")
    op.drop_column("incidents", "impact_score")
