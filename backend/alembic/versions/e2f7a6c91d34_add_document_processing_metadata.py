"""Add page number metadata to document chunks."""

from alembic import op
import sqlalchemy as sa


revision = "e2f7a6c91d34"
down_revision = "a91e6c4d2f80"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add source page number to document chunks."""

    with op.batch_alter_table("document_chunks") as batch_op:
        batch_op.add_column(
            sa.Column(
                "page_number",
                sa.Integer(),
                nullable=True,
            )
        )
        batch_op.create_check_constraint(
            "ck_document_chunks_page_number",
            "page_number IS NULL OR page_number >= 1",
        )


def downgrade() -> None:
    """Remove source page number from document chunks."""

    with op.batch_alter_table("document_chunks") as batch_op:
        batch_op.drop_constraint(
            "ck_document_chunks_page_number",
            type_="check",
        )
        batch_op.drop_column("page_number")