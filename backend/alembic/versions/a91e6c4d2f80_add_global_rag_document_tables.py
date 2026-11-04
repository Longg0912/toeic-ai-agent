"""Add global RAG document and document chunk tables."""

from alembic import op
import sqlalchemy as sa


# Revision identifiers.
revision = "a91e6c4d2f80"
down_revision = "c725be9f9c89"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create documents and document_chunks tables."""

    op.create_table(
        "documents",
        sa.Column(
            "id",
            sa.Integer(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "title",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "original_filename",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "document_type",
            sa.String(length=20),
            nullable=False,
        ),
        sa.Column(
            "storage_path",
            sa.String(length=500),
            nullable=False,
        ),
        sa.Column(
            "content_hash",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "source_name",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "source_reference",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "source_license",
            sa.String(length=200),
            nullable=True,
        ),
        sa.Column(
            "usage_permission_status",
            sa.String(length=20),
            server_default=sa.text("'unknown'"),
            nullable=False,
        ),
        sa.Column(
            "processing_status",
            sa.String(length=20),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "embedding_model",
            sa.String(length=150),
            nullable=True,
        ),
        sa.Column(
            "processing_error",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(title)) > 0",
            name="ck_documents_title_not_empty",
        ),
        sa.CheckConstraint(
            "length(trim(original_filename)) > 0",
            name="ck_documents_filename_not_empty",
        ),
        sa.CheckConstraint(
            "document_type IN ('pdf', 'docx', 'txt', 'md', 'html')",
            name="ck_documents_document_type",
        ),
        sa.CheckConstraint(
            "usage_permission_status IN "
            "('unknown', 'granted', 'restricted')",
            name="ck_documents_usage_permission",
        ),
        sa.CheckConstraint(
            "processing_status IN "
            "('pending', 'processing', 'indexed', 'failed', 'archived')",
            name="ck_documents_processing_status",
        ),
        sa.CheckConstraint(
            "length(content_hash) = 64",
            name="ck_documents_content_hash_length",
        ),
        sa.CheckConstraint(
            "length(trim(storage_path)) > 0",
            name="ck_documents_storage_path_not_empty",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "content_hash",
            name="uq_documents_content_hash",
        ),
    )

    op.create_index(
        "ix_documents_status_permission",
        "documents",
        ["processing_status", "usage_permission_status"],
        unique=False,
    )

    op.create_table(
        "document_chunks",
        sa.Column(
            "id",
            sa.Integer(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "chunk_index",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "content",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "content_hash",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "token_count",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "vector_id",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "chunk_index >= 0",
            name="ck_document_chunks_chunk_index",
        ),
        sa.CheckConstraint(
            "length(trim(content)) > 0",
            name="ck_document_chunks_content_not_empty",
        ),
        sa.CheckConstraint(
            "length(content_hash) = 64",
            name="ck_document_chunks_content_hash_length",
        ),
        sa.CheckConstraint(
            "vector_id IS NOT NULL AND length(trim(vector_id)) > 0",
            name="ck_document_chunks_vector_id_not_empty",
        ),
        sa.CheckConstraint(
            "token_count IS NULL OR token_count >= 0",
            name="ck_document_chunks_token_count",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_document_chunks_document_index",
        ),
        sa.UniqueConstraint(
            "vector_id",
            name="uq_document_chunks_vector_id",
        ),
    )

    op.create_index(
        "ix_document_chunks_document_id",
        "document_chunks",
        ["document_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop global RAG document tables."""

    op.drop_index(
        "ix_document_chunks_document_id",
        table_name="document_chunks",
    )
    op.drop_table("document_chunks")

    op.drop_index(
        "ix_documents_status_permission",
        table_name="documents",
    )
    op.drop_table("documents")