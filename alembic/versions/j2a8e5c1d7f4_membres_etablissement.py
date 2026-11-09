"""Ajoute les appartenances et rôles propres aux établissements partenaires."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "j2a8e5c1d7f4"
down_revision: Union[str, Sequence[str], None] = "i7d3f9a2c5b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "membre_etablissement",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("institution_id", sa.Integer(), sa.ForeignKey("etablissementpartenaire.id"), nullable=False),
        sa.Column("utilisateur_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="etudiant"),
        sa.Column("statut", sa.String(length=16), nullable=False, server_default="actif"),
        sa.Column("cree_par_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=True),
        sa.Column("modifie_par_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=True),
        sa.Column("date_creation", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("date_modification", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint(
            "institution_id",
            "utilisateur_id",
            name="uq_membre_etablissement_institution_utilisateur",
        ),
        sa.CheckConstraint(
            "role IN ('responsable', 'gestionnaire', 'enseignant', 'etudiant')",
            name="ck_membre_etablissement_role",
        ),
        sa.CheckConstraint(
            "statut IN ('actif', 'suspendu')",
            name="ck_membre_etablissement_statut",
        ),
    )
    op.create_index(
        "ix_membre_etablissement_institution_role_statut",
        "membre_etablissement",
        ["institution_id", "role", "statut"],
    )
    op.create_index(
        "ix_fk_membre_etablissement_institution_id",
        "membre_etablissement",
        ["institution_id"],
    )
    op.create_index(
        "ix_fk_membre_etablissement_utilisateur_id",
        "membre_etablissement",
        ["utilisateur_id"],
    )
    op.create_index(
        "ix_fk_membre_etablissement_cree_par_id",
        "membre_etablissement",
        ["cree_par_id"],
    )
    op.create_index(
        "ix_fk_membre_etablissement_modifie_par_id",
        "membre_etablissement",
        ["modifie_par_id"],
    )

    # Reprise rétrocompatible des comptes déjà rattachés à un établissement.
    # Le rôle global n'est jamais modifié : un PROFESSEUR devient seulement
    # enseignant dans l'organisation concernée, les autres comptes apprenants.
    bind = op.get_bind()
    bind.execute(sa.text(
        """
        INSERT INTO membre_etablissement (
            institution_id, utilisateur_id, role, statut, date_creation, date_modification
        )
        SELECT
            institution_id,
            id,
            CASE WHEN CAST(role AS VARCHAR(30)) = 'professeur'
                 THEN 'enseignant' ELSE 'etudiant' END,
            'actif',
            COALESCE(date_creation, CURRENT_TIMESTAMP),
            CURRENT_TIMESTAMP
        FROM utilisateur
        WHERE institution_id IS NOT NULL
        """
    ))

    if bind.dialect.name == "postgresql":
        roles = bind.execute(
            sa.text("SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')")
        ).scalars().all()
        quote = bind.dialect.identifier_preparer.quote
        bind.exec_driver_sql("ALTER TABLE public.membre_etablissement ENABLE ROW LEVEL SECURITY")
        bind.exec_driver_sql("REVOKE ALL PRIVILEGES ON TABLE public.membre_etablissement FROM PUBLIC")
        for role in roles:
            if role in {"anon", "authenticated"}:
                bind.exec_driver_sql(
                    "REVOKE ALL PRIVILEGES ON TABLE public.membre_etablissement FROM " + quote(role)
                )


def downgrade() -> None:
    op.drop_index("ix_fk_membre_etablissement_modifie_par_id", table_name="membre_etablissement")
    op.drop_index("ix_fk_membre_etablissement_cree_par_id", table_name="membre_etablissement")
    op.drop_index("ix_fk_membre_etablissement_utilisateur_id", table_name="membre_etablissement")
    op.drop_index("ix_fk_membre_etablissement_institution_id", table_name="membre_etablissement")
    op.drop_index("ix_membre_etablissement_institution_role_statut", table_name="membre_etablissement")
    op.drop_table("membre_etablissement")
