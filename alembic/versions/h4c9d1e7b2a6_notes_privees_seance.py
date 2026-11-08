"""Ajoute les notes personnelles privées des séances virtuelles."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "h4c9d1e7b2a6"
down_revision: Union[str, Sequence[str], None] = "g2a7f5d9c1e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "noteseance",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("seance_id", sa.Integer(), sa.ForeignKey("seance.id"), nullable=False),
        sa.Column("cours_id", sa.Integer(), sa.ForeignKey("cours.id"), nullable=False),
        sa.Column("utilisateur_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=False),
        sa.Column("contenu", sa.String(length=30000), nullable=False, server_default=""),
        sa.Column("date_creation", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("date_modification", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("seance_id", "utilisateur_id", name="uq_noteseance_seance_utilisateur"),
    )
    op.create_index("ix_noteseance_seance_id", "noteseance", ["seance_id"])
    op.create_index("ix_noteseance_cours_id", "noteseance", ["cours_id"])
    op.create_index("ix_noteseance_utilisateur_id", "noteseance", ["utilisateur_id"])
    op.create_index("ix_noteseance_cours_utilisateur", "noteseance", ["cours_id", "utilisateur_id"])

    # La Data API Supabase ne doit pas pouvoir lire ces notes. L'application
    # utilise sa connexion PostgreSQL serveur ; aucun accès direct client n'est requis.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.exec_driver_sql("ALTER TABLE public.noteseance ENABLE ROW LEVEL SECURITY")
        bind.exec_driver_sql("REVOKE ALL PRIVILEGES ON TABLE public.noteseance FROM PUBLIC")
        roles = bind.execute(
            sa.text("SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')")
        ).scalars().all()
        quote = bind.dialect.identifier_preparer.quote
        for role in roles:
            if role in {"anon", "authenticated"}:
                bind.exec_driver_sql(
                    "REVOKE ALL PRIVILEGES ON TABLE public.noteseance FROM " + quote(role)
                )


def downgrade() -> None:
    op.drop_index("ix_noteseance_cours_utilisateur", table_name="noteseance")
    op.drop_index("ix_noteseance_utilisateur_id", table_name="noteseance")
    op.drop_index("ix_noteseance_cours_id", table_name="noteseance")
    op.drop_index("ix_noteseance_seance_id", table_name="noteseance")
    op.drop_table("noteseance")
