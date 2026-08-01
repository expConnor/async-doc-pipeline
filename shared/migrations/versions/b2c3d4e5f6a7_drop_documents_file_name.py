"""drop_documents_file_name

DESTRUCTIVE. Drops documents.file_name. The column held an unverified
client-supplied label that the API could never validate, since uploads go
directly to S3 and the API never sees the file. Its values are not
recoverable by downgrade.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-01

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema. Destroys all stored file names."""
    op.drop_column("documents", "file_name")


def downgrade() -> None:
    """Downgrade schema. Recreates the column empty — values are lost."""
    op.add_column(
        "documents",
        sa.Column(
            "file_name", sa.String(), nullable=False, server_default=""
        ),
    )
    op.alter_column("documents", "file_name", server_default=None)
