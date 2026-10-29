"""Add Ed25519 signature to evidence packages

The existing `signature` column is an HMAC keyed by the service secret: it
proves a package is ours, but only to someone who already holds that secret.
An Ed25519 signature over the same clip digest can be checked by anyone holding
the public key, which is what makes an evidence package useful outside the
system that produced it.

Revision ID: 003
Revises: 002
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable: packages created before this migration have no Ed25519
    # signature and must not be made to look as if they do.
    op.add_column(
        "evidence_packages",
        sa.Column("ed25519_signature", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("evidence_packages", "ed25519_signature")
