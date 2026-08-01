"""uuid_primary_keys

DESTRUCTIVE. Postgres cannot cast integer to uuid, so no existing document,
job, or artifact rows can survive this migration. It truncates all three
tables explicitly rather than depending on being run against an empty
database. Accounts are untouched.

Revision ID: a1b2c3d4e5f6
Revises: 29e93f1a2527
Create Date: 2026-08-01

"""

from typing import Sequence, Union

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "29e93f1a2527"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("documents", "jobs", "artifacts")


def upgrade() -> None:
    """Upgrade schema. Destroys all document, job, and artifact rows."""
    # The partial index and the foreign keys both reference columns whose
    # type is about to change; Postgres will not alter a column underneath
    # them.
    op.execute("DROP INDEX IF EXISTS one_active_job_per_document")
    op.execute(
        "ALTER TABLE artifacts DROP CONSTRAINT IF EXISTS artifacts_job_id_fkey"
    )
    op.execute(
        "ALTER TABLE artifacts "
        "DROP CONSTRAINT IF EXISTS artifacts_document_id_fkey"
    )
    op.execute(
        "ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_document_id_fkey"
    )

    op.execute("TRUNCATE artifacts, jobs, documents CASCADE")

    # Each id is SERIAL, so the nextval() default must go before the type
    # change and the now-orphaned sequence after it.
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN id DROP DEFAULT")
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN id TYPE uuid "
            f"USING gen_random_uuid()"
        )
        op.execute(f"DROP SEQUENCE IF EXISTS {table}_id_seq")

    op.execute(
        "ALTER TABLE jobs ALTER COLUMN document_id TYPE uuid "
        "USING gen_random_uuid()"
    )
    op.execute(
        "ALTER TABLE artifacts ALTER COLUMN document_id TYPE uuid "
        "USING gen_random_uuid()"
    )
    op.execute(
        "ALTER TABLE artifacts ALTER COLUMN job_id TYPE uuid "
        "USING gen_random_uuid()"
    )

    op.create_foreign_key(
        "jobs_document_id_fkey", "jobs", "documents", ["document_id"], ["id"]
    )
    op.create_foreign_key(
        "artifacts_document_id_fkey",
        "artifacts",
        "documents",
        ["document_id"],
        ["id"],
    )
    op.create_foreign_key(
        "artifacts_job_id_fkey", "artifacts", "jobs", ["job_id"], ["id"]
    )

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


def downgrade() -> None:
    """Downgrade schema. Equally destructive — uuid cannot cast to integer."""
    op.execute("DROP INDEX IF EXISTS one_active_job_per_document")
    op.execute(
        "ALTER TABLE artifacts DROP CONSTRAINT IF EXISTS artifacts_job_id_fkey"
    )
    op.execute(
        "ALTER TABLE artifacts "
        "DROP CONSTRAINT IF EXISTS artifacts_document_id_fkey"
    )
    op.execute(
        "ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_document_id_fkey"
    )

    op.execute("TRUNCATE artifacts, jobs, documents CASCADE")

    op.execute("ALTER TABLE jobs ALTER COLUMN document_id TYPE integer USING 0")
    op.execute(
        "ALTER TABLE artifacts ALTER COLUMN document_id TYPE integer USING 0"
    )
    op.execute("ALTER TABLE artifacts ALTER COLUMN job_id TYPE integer USING 0")

    for table in _TABLES:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN id TYPE integer USING 0"
        )
        op.execute(f"CREATE SEQUENCE {table}_id_seq OWNED BY {table}.id")
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN id "
            f"SET DEFAULT nextval('{table}_id_seq')"
        )

    op.create_foreign_key(
        "jobs_document_id_fkey", "jobs", "documents", ["document_id"], ["id"]
    )
    op.create_foreign_key(
        "artifacts_document_id_fkey",
        "artifacts",
        "documents",
        ["document_id"],
        ["id"],
    )
    op.create_foreign_key(
        "artifacts_job_id_fkey", "artifacts", "jobs", ["job_id"], ["id"]
    )

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
