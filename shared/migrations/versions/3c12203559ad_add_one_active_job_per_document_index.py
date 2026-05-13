"""add_one_active_job_per_document_index

Revision ID: 3c12203559ad
Revises: c3890ddba5ac
Create Date: 2026-05-13 07:44:13.049042

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3c12203559ad"
down_revision: Union[str, Sequence[str], None] = "c3890ddba5ac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        CREATE UNIQUE INDEX one_active_job_per_document
        ON jobs (account_id, document_id)
        WHERE status IN (
            'CREATED'::job_status_enum,
            'QUEUED'::job_status_enum,
            'STARTED'::job_status_enum
        )
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS one_active_job_per_document")
