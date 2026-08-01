"""artifact_unique_document_type

Moves artifact uniqueness from object_key to (document_id, artifact_type).
The key is derived from exactly those two fields, so a separate constraint
on object_key would encode one rule twice.

DESTRUCTIVE. Existing artifact rows are truncated: pre-existing keys are
job-scoped, so more than one row can share a (document_id, artifact_type)
pair and the new constraint would fail to build.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-01

"""

from typing import Sequence, Union

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema. Destroys all artifact rows."""
    op.execute("TRUNCATE artifacts")
    op.execute(
        "ALTER TABLE artifacts "
        "DROP CONSTRAINT IF EXISTS artifacts_object_key_key"
    )
    op.create_unique_constraint(
        "artifacts_document_id_artifact_type_key",
        "artifacts",
        ["document_id", "artifact_type"],
    )


def downgrade() -> None:
    """Downgrade schema. Destroys all artifact rows."""
    op.execute("TRUNCATE artifacts")
    op.drop_constraint(
        "artifacts_document_id_artifact_type_key",
        "artifacts",
        type_="unique",
    )
    op.create_unique_constraint(
        "artifacts_object_key_key", "artifacts", ["object_key"]
    )
