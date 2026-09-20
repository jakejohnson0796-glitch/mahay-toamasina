"""Securisation Storage Supabase et index de performance."""

from typing import Sequence, Union
import os

from alembic import op
import sqlalchemy as sa


revision: str = "f7c2d9a4e1b6"
down_revision: Union[str, None] = "0eeeb4371250"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BUCKET_ID = os.getenv("SUPABASE_BUCKET", "documents")
FILE_SIZE_LIMIT = 20 * 1024 * 1024
ALLOWED_MIMES = (
    "application/pdf,application/msword,"
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document,"
    "application/vnd.ms-powerpoint,"
    "application/vnd.openxmlformats-officedocument.presentationml.presentation,"
    "image/jpeg,image/png,image/webp"
)


def upgrade() -> None:
    op.create_index("ix_document_statut", "document", ["statut"])
    op.create_index("ix_document_cercle_id", "document", ["cercle_id"])
    op.create_index("ix_tentativequiz_utilisateur_id", "tentativequiz", ["utilisateur_id"])
    op.create_index("ix_membrecercle_cercle_id", "membrecercle", ["cercle_id"])
    op.create_index("ix_membrecercle_utilisateur_id", "membrecercle", ["utilisateur_id"])

    if op.get_bind().dialect.name != "postgresql":
        return

    exists = op.get_bind().execute(
        sa.text("SELECT 1 FROM storage.buckets WHERE id = :bucket").bindparams(bucket=BUCKET_ID)
    ).scalar()
    if not exists:
        raise RuntimeError(f"Le bucket Supabase '{BUCKET_ID}' doit exister avant cette migration.")

    op.execute(sa.text(
        """
        UPDATE storage.buckets
        SET public = FALSE,
            file_size_limit = :limit,
            allowed_mime_types = CAST(:mimes AS text[])
        WHERE id = :bucket
        """
    ).bindparams(
        limit=FILE_SIZE_LIMIT,
        mimes="{" + ALLOWED_MIMES.replace(",", ",") + "}",
        bucket=BUCKET_ID,
    ))


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text(
            "UPDATE storage.buckets SET public = TRUE, file_size_limit = NULL, allowed_mime_types = NULL WHERE id = :bucket"
        ).bindparams(bucket=BUCKET_ID))

    op.drop_index("ix_membrecercle_utilisateur_id", table_name="membrecercle")
    op.drop_index("ix_membrecercle_cercle_id", table_name="membrecercle")
    op.drop_index("ix_tentativequiz_utilisateur_id", table_name="tentativequiz")
    op.drop_index("ix_document_cercle_id", table_name="document")
    op.drop_index("ix_document_statut", table_name="document")
