"""Add crowd_threshold event type. Batch mode: SQLite can't ALTER a CHECK
constraint in place, only rebuild the table.

Revision ID: 008
Revises: 007
Create Date: 2026-09-12

"""
from typing import Sequence, Union

from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OLD_EVENT_TYPES = (
    "restricted_zone_entry", "after_hours_presence", "loitering",
    "camera_offline", "camera_frozen", "camera_blackout",
    "camera_blur", "fall_warning", "abandoned_object_warning",
    "fire_smoke_warning", "line_crossing",
)
NEW_EVENT_TYPES = OLD_EVENT_TYPES + ("crowd_threshold",)


def _in_list(values: tuple) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    with op.batch_alter_table("observations", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_observations_event_type", type_="check")
        batch_op.create_check_constraint(
            "ck_observations_event_type", f"event_type IN ({_in_list(NEW_EVENT_TYPES)})"
        )


def downgrade() -> None:
    with op.batch_alter_table("observations", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_observations_event_type", type_="check")
        batch_op.create_check_constraint(
            "ck_observations_event_type", f"event_type IN ({_in_list(OLD_EVENT_TYPES)})"
        )
