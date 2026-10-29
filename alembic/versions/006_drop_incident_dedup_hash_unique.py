"""Drop the erroneous global UNIQUE constraint on incidents.dedup_hash.

dedup_hash is only meant to merge OPEN incidents of the same
camera+event_type+5-minute window (incidents/correlator.py already scopes
its own duplicate check to open statuses) — the same hash legitimately
recurs once an earlier incident for that window is closed and the same
event type fires again. The DB-level unique constraint was wrong and
crashed the correlator on exactly that common, everyday case.

A naming_convention is supplied so batch mode can name (and then target)
a constraint that was created unnamed in migration 001.

Revision ID: 006
Revises: 005
Create Date: 2026-09-11

"""
from typing import Sequence, Union

from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NAMING_CONVENTION = {"uq": "uq_%(table_name)s_%(column_0_name)s"}


def upgrade() -> None:
    with op.batch_alter_table(
        "incidents", recreate="always", naming_convention=NAMING_CONVENTION
    ) as batch_op:
        batch_op.drop_constraint("uq_incidents_dedup_hash", type_="unique")


def downgrade() -> None:
    with op.batch_alter_table(
        "incidents", recreate="always", naming_convention=NAMING_CONVENTION
    ) as batch_op:
        batch_op.create_unique_constraint("uq_incidents_dedup_hash", ["dedup_hash"])
