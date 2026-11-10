
"""Add document ownership for Personal RAG."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1a9c3d7e205"
down_revision: Union[str, Sequence[str], None] = (
    "e2f7a6c91d34"
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add document ownership and scoped content uniqueness."""

    # SQLite needs a table rebuild to replace the old unique
    # constraint with partial unique indexes.
    with op.batch_alter_table(
        "documents",
        recreate="always",
    ) as batch_op:
        batch_op.add_column(
            sa.Column(
                "owner_user_id",
                sa.Integer(),
                nullable=True,
            )
        )

        batch_op.create_foreign_key(
            "fk_documents_owner_user_id_users",
            "users",
            ["owner_user_id"],
            ["id"],
            ondelete="CASCADE",
        )

        batch_op.drop_constraint(
            "uq_documents_content_hash",
            type_="unique",
        )

    # Global documents must have unique content hashes.
    op.create_index(
        "uq_documents_global_content_hash",
        "documents",
        ["content_hash"],
        unique=True,
        sqlite_where=sa.text("owner_user_id IS NULL"),
    )

    # Personal documents are unique only within each owner.
    op.create_index(
        "uq_documents_personal_owner_hash",
        "documents",
        ["owner_user_id", "content_hash"],
        unique=True,
        sqlite_where=sa.text("owner_user_id IS NOT NULL"),
    )

    op.create_index(
        "ix_documents_owner_status",
        "documents",
        ["owner_user_id", "processing_status"],
        unique=False,
    )


def downgrade() -> None:
    """Revert ownership changes safely."""

    bind = op.get_bind()

    duplicate_count = bind.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM (
                SELECT content_hash
                FROM documents
                GROUP BY content_hash
                HAVING COUNT(*) > 1
            )
            """
        )
    ).scalar_one()

    if duplicate_count:
        raise RuntimeError(
            "Cannot downgrade: duplicate document content hashes "
            "exist across different owners."
        )

    op.drop_index(
        "ix_documents_owner_status",
        table_name="documents",
    )

    op.drop_index(
        "uq_documents_personal_owner_hash",
        table_name="documents",
    )

    op.drop_index(
        "uq_documents_global_content_hash",
        table_name="documents",
    )

    with op.batch_alter_table(
        "documents",
        recreate="always",
    ) as batch_op:
        batch_op.drop_constraint(
            "fk_documents_owner_user_id_users",
            type_="foreignkey",
        )

        batch_op.drop_column("owner_user_id")

        batch_op.create_unique_constraint(
            "uq_documents_content_hash",
            ["content_hash"],
        )
