"""Ajoute les rattachements parent/élève vérifiés et audités."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "j8a4c2d7e9f1"
down_revision: Union[str, Sequence[str], None] = "j2a8e5c1d7f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lienresponsableeleve",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("responsable_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=True),
        sa.Column("eleve_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=True),
        sa.Column("type_lien", sa.String(length=24), nullable=False, server_default="parent"),
        sa.Column("statut", sa.String(length=16), nullable=False, server_default="actif"),
        sa.Column("verifie_par_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=True),
        sa.Column("date_verification", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("date_creation", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("revoque_par_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=True),
        sa.Column("date_revocation", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("responsable_id", "eleve_id", name="uq_lienresponsableeleve_pair"),
        sa.CheckConstraint("responsable_id <> eleve_id", name="ck_lienresponsableeleve_distinct"),
        sa.CheckConstraint(
            "type_lien IN ('parent', 'tuteur_legal', 'responsable_autorise')",
            name="ck_lienresponsableeleve_type",
        ),
        sa.CheckConstraint("statut IN ('actif', 'revoque')", name="ck_lienresponsableeleve_statut"),
    )
    op.create_index(
        "ix_lienresponsableeleve_responsable_id",
        "lienresponsableeleve",
        ["responsable_id"],
    )
    op.create_index(
        "ix_lienresponsableeleve_eleve_id",
        "lienresponsableeleve",
        ["eleve_id"],
    )
    op.create_index(
        "ix_lienresponsableeleve_statut",
        "lienresponsableeleve",
        ["statut"],
    )
    op.create_index(
        "ix_lienresponsableeleve_responsable_statut",
        "lienresponsableeleve",
        ["responsable_id", "statut"],
    )
    op.create_index(
        "ix_lienresponsableeleve_eleve_statut",
        "lienresponsableeleve",
        ["eleve_id", "statut"],
    )

    op.create_table(
        "evenementlienresponsableeleve",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("lien_id", sa.Integer(), sa.ForeignKey("lienresponsableeleve.id"), nullable=False),
        sa.Column("acteur_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=True),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("type_lien", sa.String(length=24), nullable=False),
        sa.Column("date_evenement", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.CheckConstraint(
            "action IN ('validation', 'reactivation', 'revocation')",
            name="ck_evenementlienresponsable_action",
        ),
    )
    op.create_index(
        "ix_evenementlienresponsableeleve_lien_id",
        "evenementlienresponsableeleve",
        ["lien_id"],
    )
    op.create_index(
        "ix_evenementlienresponsableeleve_acteur_id",
        "evenementlienresponsableeleve",
        ["acteur_id"],
    )
    op.create_index(
        "ix_evenementlienresponsableeleve_action",
        "evenementlienresponsableeleve",
        ["action"],
    )
    op.create_index(
        "ix_evenementlienresponsableeleve_date_evenement",
        "evenementlienresponsableeleve",
        ["date_evenement"],
    )

    # Aucun accès direct à cette table via la Data API Supabase.
    # Les vérifications d'autorisation sont faites par l'application serveur.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.exec_driver_sql("ALTER TABLE public.lienresponsableeleve ENABLE ROW LEVEL SECURITY")
        bind.exec_driver_sql("ALTER TABLE public.evenementlienresponsableeleve ENABLE ROW LEVEL SECURITY")
        bind.exec_driver_sql("REVOKE ALL PRIVILEGES ON TABLE public.lienresponsableeleve FROM PUBLIC")
        bind.exec_driver_sql("REVOKE ALL PRIVILEGES ON TABLE public.evenementlienresponsableeleve FROM PUBLIC")
        roles = bind.execute(
            sa.text("SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')")
        ).scalars().all()
        quote = bind.dialect.identifier_preparer.quote
        for role in roles:
            if role in {"anon", "authenticated"}:
                bind.exec_driver_sql(
                    "REVOKE ALL PRIVILEGES ON TABLE public.lienresponsableeleve FROM " + quote(role)
                )
                bind.exec_driver_sql(
                    "REVOKE ALL PRIVILEGES ON TABLE public.evenementlienresponsableeleve FROM " + quote(role)
                )


def downgrade() -> None:
    op.drop_index("ix_evenementlienresponsableeleve_date_evenement", table_name="evenementlienresponsableeleve")
    op.drop_index("ix_evenementlienresponsableeleve_action", table_name="evenementlienresponsableeleve")
    op.drop_index("ix_evenementlienresponsableeleve_acteur_id", table_name="evenementlienresponsableeleve")
    op.drop_index("ix_evenementlienresponsableeleve_lien_id", table_name="evenementlienresponsableeleve")
    op.drop_table("evenementlienresponsableeleve")
    op.drop_index("ix_lienresponsableeleve_eleve_statut", table_name="lienresponsableeleve")
    op.drop_index("ix_lienresponsableeleve_responsable_statut", table_name="lienresponsableeleve")
    op.drop_index("ix_lienresponsableeleve_statut", table_name="lienresponsableeleve")
    op.drop_index("ix_lienresponsableeleve_eleve_id", table_name="lienresponsableeleve")
    op.drop_index("ix_lienresponsableeleve_responsable_id", table_name="lienresponsableeleve")
    op.drop_table("lienresponsableeleve")
