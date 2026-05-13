"""remove_created_from_job_status_enum

Revision ID: 29e93f1a2527
Revises: 3c12203559ad
Create Date: 2026-05-13 08:41:37.314494

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "29e93f1a2527"
down_revision: Union[str, Sequence[str], None] = "3c12203559ad"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Backfill any rows stranded in CREATED before this fix
    op.execute(
        """
        UPDATE jobs
        SET status = 'QUEUED', queued_at = NOW()
        WHERE status = 'CREATED'
        """
    )

    # Drop index before altering the enum type it references
    op.execute("DROP INDEX one_active_job_per_document")

    # Drop the column default before changing the type
    # (default references old enum)
    op.execute("ALTER TABLE jobs ALTER COLUMN status DROP DEFAULT")

    # Recreate the enum without CREATED
    op.execute(
        """
        CREATE TYPE job_status_enum_new
        AS ENUM ('QUEUED', 'STARTED', 'COMPLETED', 'FAILED')
        """
    )
    op.execute(
        """
        ALTER TABLE jobs ALTER COLUMN status TYPE job_status_enum_new
        USING status::text::job_status_enum_new
        """
    )
    op.execute("DROP TYPE job_status_enum")
    op.execute("ALTER TYPE job_status_enum_new RENAME TO job_status_enum")

    # Recreate the partial unique index without CREATED
    op.execute(
        """
        CREATE UNIQUE INDEX one_active_job_per_document
        ON jobs (account_id, document_id)
        WHERE status IN (
            'QUEUED'::job_status_enum,
            'STARTED'::job_status_enum
        )
        """
    )

    # Update the column server_default
    op.execute(
        """
        ALTER TABLE jobs
        ALTER COLUMN status SET DEFAULT 'QUEUED'::job_status_enum
        """
    )


def downgrade() -> None:
    # Drop index before altering the enum type it references
    op.execute("DROP INDEX one_active_job_per_document")

    # Drop the column default before changing the type
    # (default references old enum)
    op.execute("ALTER TABLE jobs ALTER COLUMN status DROP DEFAULT")

    # Recreate enum with CREATED
    # Must happen before setting CREATED as default
    op.execute(
        """
        CREATE TYPE job_status_enum_old
        AS ENUM ('CREATED', 'QUEUED', 'STARTED', 'COMPLETED', 'FAILED')
        """
    )
    op.execute(
        """
        ALTER TABLE jobs ALTER COLUMN status TYPE job_status_enum_old
        USING status::text::job_status_enum_old
        """
    )
    op.execute("DROP TYPE job_status_enum")
    op.execute("ALTER TYPE job_status_enum_old RENAME TO job_status_enum")

    # Now CREATED exists in the enum — safe to set as default
    op.execute(
        """
        ALTER TABLE jobs
        ALTER COLUMN status SET DEFAULT 'CREATED'::job_status_enum
        """
    )

    # Restore partial index with CREATED
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
