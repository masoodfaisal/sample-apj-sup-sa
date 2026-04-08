"""Add per-model Bedrock region support."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "002_bedrock_region"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("model_catalog", sa.Column("bedrock_region", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("model_catalog", "bedrock_region")
