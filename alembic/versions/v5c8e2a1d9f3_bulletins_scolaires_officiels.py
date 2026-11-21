"""Crée les bulletins scolaires publiables et leur journal d'audit."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "v5c8e2a1d9f3"
down_revision: Union[str, Sequence[str], None] = "u4b7e2c9f1a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bulletinscolaire",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("cours_id", sa.Integer(), sa.ForeignKey("cours.id"), nullable=False),
        sa.Column("utilisateur_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=False),
        sa.Column("periode", sa.String(length=40), nullable=False),
        sa.Column("appreciation", sa.String(length=2000), nullable=True),
        sa.Column("statut", sa.String(length=16), nullable=False, server_default="brouillon"),
        sa.Column("cree_par_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=True),
        sa.Column("publie_par_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=True),
        sa.Column("date_creation", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("date_modification", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("date_publication", sa.DateTime(), nullable=True),
        sa.Column("snapshot_json", sa.Text(), nullable=False, server_default="{}"),
        sa.UniqueConstraint(
            "cours_id", "utilisateur_id", "periode",
            name="uq_bulletinscolaire_cours_eleve_periode",
        ),
        sa.CheckConstraint(
            "statut IN ('brouillon', 'publie')",
            name="ck_bulletinscolaire_statut",
        ),
    )
    op.create_index("ix_bulletinscolaire_cours_id", "bulletinscolaire", ["cours_id"])
    op.create_index("ix_bulletinscolaire_utilisateur_id", "bulletinscolaire", ["utilisateur_id"])
    op.create_index("ix_bulletinscolaire_statut", "bulletinscolaire", ["statut"])
    op.create_index(
        "ix_bulletinscolaire_cours_periode_statut",
        "bulletinscolaire",
        ["cours_id", "periode", "statut"],
    )
    op.create_index(
        "ix_bulletinscolaire_eleve_statut_publication",
        "bulletinscolaire",
        ["utilisateur_id", "statut", "date_publication"],
    )

    op.create_table(
        "bulletinscolaireevenement",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("bulletin_id", sa.Integer(), sa.ForeignKey("bulletinscolaire.id"), nullable=False),
        sa.Column("acteur_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=True),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("date_evenement", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.CheckConstraint(
            "action IN ('creation', 'modification', 'publication', 'reouverture')",
            name="ck_bulletinscolaireevenement_action",
        ),
    )
    op.create_index(
        "ix_bulletinscolaireevenement_bulletin_id",
        "bulletinscolaireevenement",
        ["bulletin_id"],
    )
    op.create_index(
        "ix_bulletinscolaireevenement_acteur_id",
        "bulletinscolaireevenement",
        ["acteur_id"],
    )
    op.create_index(
        "ix_bulletinscolaireevenement_action",
        "bulletinscolaireevenement",
        ["action"],
    )
    op.create_index(
        "ix_bulletinscolaireevenement_date_evenement",
        "bulletinscolaireevenement",
        ["date_evenement"],
    )

    # Les tables ne sont jamais exposées à la Data API Supabase.
    # Toutes les lectures/écritures passent par les routes serveur et leurs
    # vérifications de rôle, propriétaire du cours et lien familial actif.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in ("bulletinscolaire", "bulletinscolaireevenement"):
            bind.exec_driver_sql(
                f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY"
            )
            bind.exec_driver_sql(
                f"REVOKE ALL PRIVILEGES ON TABLE public.{table} FROM PUBLIC"
            )
        roles = bind.execute(
            sa.text("SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')")
        ).scalars().all()
        quote = bind.dialect.identifier_preparer.quote
        for role in roles:
            if role in {"anon", "authenticated"}:
                for table in ("bulletinscolaire", "bulletinscolaireevenement"):
                    bind.exec_driver_sql(
                        f"REVOKE ALL PRIVILEGES ON TABLE public.{table} FROM " + quote(role)
                    )


def downgrade() -> None:
    op.drop_index("ix_bulletinscolaireevenement_date_evenement", table_name="bulletinscolaireevenement")
    op.drop_index("ix_bulletinscolaireevenement_action", table_name="bulletinscolaireevenement")
    op.drop_index("ix_bulletinscolaireevenement_acteur_id", table_name="bulletinscolaireevenement")
    op.drop_index("ix_bulletinscolaireevenement_bulletin_id", table_name="bulletinscolaireevenement")
    op.drop_table("bulletinscolaireevenement")
    op.drop_index("ix_bulletinscolaire_eleve_statut_publication", table_name="bulletinscolaire")
    op.drop_index("ix_bulletinscolaire_cours_periode_statut", table_name="bulletinscolaire")
    op.drop_index("ix_bulletinscolaire_statut", table_name="bulletinscolaire")
    op.drop_index("ix_bulletinscolaire_utilisateur_id", table_name="bulletinscolaire")
    op.drop_index("ix_bulletinscolaire_cours_id", table_name="bulletinscolaire")
    op.drop_table("bulletinscolaire")
