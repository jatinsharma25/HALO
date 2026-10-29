"""Add camera_blur, fall_warning, abandoned_object_warning event types and a
'blurred' camera status. Batch mode: SQLite can't ALTER a CHECK constraint
in place, only rebuild the table.

Revision ID: 005
Revises: 004
Create Date: 2026-09-10

"""
from typing import Sequence, Union

from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OLD_EVENT_TYPES = (
    "restricted_zone_entry", "after_hours_presence", "loitering",
    "camera_offline", "camera_frozen", "camera_blackout",
)
NEW_EVENT_TYPES = OLD_EVENT_TYPES + ("camera_blur", "fall_warning", "abandoned_object_warning")

OLD_CAMERA_STATUSES = ("active", "offline", "frozen", "blackout", "unknown")
NEW_CAMERA_STATUSES = OLD_CAMERA_STATUSES + ("blurred",)


def _in_list(values: tuple) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    with op.batch_alter_table("observations", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_observations_event_type", type_="check")
        batch_op.create_check_constraint(
            "ck_observations_event_type", f"event_type IN ({_in_list(NEW_EVENT_TYPES)})"
        )

    with op.batch_alter_table("cameras", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_cameras_status", type_="check")
        batch_op.create_check_constraint(
            "ck_cameras_status", f"status IN ({_in_list(NEW_CAMERA_STATUSES)})"
        )


def downgrade() -> None:
    with op.batch_alter_table("cameras", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_cameras_status", type_="check")
        batch_op.create_check_constraint(
            "ck_cameras_status", f"status IN ({_in_list(OLD_CAMERA_STATUSES)})"
        )

    with op.batch_alter_table("observations", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_observations_event_type", type_="check")
        batch_op.create_check_constraint(
            "ck_observations_event_type", f"event_type IN ({_in_list(OLD_EVENT_TYPES)})"
        )
