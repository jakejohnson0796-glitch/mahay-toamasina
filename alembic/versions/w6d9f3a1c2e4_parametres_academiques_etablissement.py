"""Ajoute les paramètres pédagogiques par établissement et année scolaire."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "w6d9f3a1c2e4"
down_revision: Union[str, Sequence[str], None] = "v5c8e2a1d9f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "parametresacademiquesetablissement",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "etablissement_id",
            sa.Integer(),
            sa.ForeignKey("etablissementscolaire.id"),
            nullable=False,
        ),
        sa.Column("annee_scolaire", sa.String(length=9), nullable=False),
        sa.Column("calendrier", sa.String(length=20), nullable=False, server_default="trimestre"),
        sa.Column(
            "periodes_json",
            sa.String(),
            nullable=False,
            server_default='[{"code":"T1","libelle":"Trimestre 1"},{"code":"T2","libelle":"Trimestre 2"},{"code":"T3","libelle":"Trimestre 3"}]',
        ),
        sa.Column("note_maximale", sa.Float(), nullable=False, server_default=sa.text("20.0")),
        sa.Column("seuil_reussite", sa.Float(), nullable=False, server_default=sa.text("10.0")),
        sa.Column("est_actif", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("date_creation", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("date_modification", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint(
            "etablissement_id",
            "annee_scolaire",
            name="uq_parametresacademiques_etablissement_annee",
        ),
        sa.CheckConstraint(
            "calendrier IN ('trimestre', 'semestre', 'personnalise')",
            name="ck_parametresacademiques_calendrier",
        ),
        sa.CheckConstraint(
            "note_maximale >= 1 AND note_maximale <= 1000",
            name="ck_parametresacademiques_note_maximale",
        ),
        sa.CheckConstraint(
            "seuil_reussite >= 0 AND seuil_reussite <= note_maximale",
            name="ck_parametresacademiques_seuil_reussite",
        ),
    )
    op.create_index(
        "ix_parametresacademiquesetablissement_etablissement_id",
        "parametresacademiquesetablissement",
        ["etablissement_id"],
    )
    op.create_index(
        "ix_parametresacademiquesetablissement_annee_scolaire",
        "parametresacademiquesetablissement",
        ["annee_scolaire"],
    )
    op.create_index(
        "ix_parametresacademiquesetablissement_est_actif",
        "parametresacademiquesetablissement",
        ["est_actif"],
    )
    op.create_index(
        "ix_parametresacademiques_etablissement_actif",
        "parametresacademiquesetablissement",
        ["etablissement_id", "est_actif"],
    )

    op.create_table(
        "coefficientmatiereetablissement",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "parametres_id",
            sa.Integer(),
            sa.ForeignKey("parametresacademiquesetablissement.id"),
            nullable=False,
        ),
        sa.Column("niveau_id", sa.Integer(), sa.ForeignKey("niveauscolaire.id"), nullable=False),
        sa.Column("option_id", sa.Integer(), sa.ForeignKey("optionscolaire.id"), nullable=True),
        sa.Column("matiere_id", sa.Integer(), sa.ForeignKey("matierescolaire.id"), nullable=False),
        sa.Column("coefficient", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("obligatoire", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("date_creation", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("date_modification", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.CheckConstraint(
            "coefficient > 0 AND coefficient <= 100",
            name="ck_coefficientmatiere_valeur",
        ),
    )
    op.create_index(
        "ix_coefficientmatiereetablissement_parametres_id",
        "coefficientmatiereetablissement",
        ["parametres_id"],
    )
    op.create_index(
        "ix_coefficientmatiereetablissement_niveau_id",
        "coefficientmatiereetablissement",
        ["niveau_id"],
    )
    op.create_index(
        "ix_coefficientmatiereetablissement_option_id",
        "coefficientmatiereetablissement",
        ["option_id"],
    )
    op.create_index(
        "ix_coefficientmatiereetablissement_matiere_id",
        "coefficientmatiereetablissement",
        ["matiere_id"],
    )
    op.create_index(
        "uq_coefficientmatiere_avec_option",
        "coefficientmatiereetablissement",
        ["parametres_id", "niveau_id", "option_id", "matiere_id"],
        unique=True,
        sqlite_where=sa.text("option_id IS NOT NULL"),
        postgresql_where=sa.text("option_id IS NOT NULL"),
    )
    op.create_index(
        "uq_coefficientmatiere_sans_option",
        "coefficientmatiereetablissement",
        ["parametres_id", "niveau_id", "matiere_id"],
        unique=True,
        sqlite_where=sa.text("option_id IS NULL"),
        postgresql_where=sa.text("option_id IS NULL"),
    )

    # Les tables sont utilisées uniquement par l'application serveur.
    # Aucune lecture/écriture directe par la Data API Supabase n'est autorisée.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in (
            "parametresacademiquesetablissement",
            "coefficientmatiereetablissement",
        ):
            bind.exec_driver_sql(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
            bind.exec_driver_sql(f"REVOKE ALL PRIVILEGES ON TABLE public.{table} FROM PUBLIC")
        roles = bind.execute(
            sa.text("SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')")
        ).scalars().all()
        quote = bind.dialect.identifier_preparer.quote
        for role in roles:
            if role in {"anon", "authenticated"}:
                for table in (
                    "parametresacademiquesetablissement",
                    "coefficientmatiereetablissement",
                ):
                    bind.exec_driver_sql(
                        f"REVOKE ALL PRIVILEGES ON TABLE public.{table} FROM " + quote(role)
                    )


def downgrade() -> None:
    op.drop_index("uq_coefficientmatiere_sans_option", table_name="coefficientmatiereetablissement")
    op.drop_index("uq_coefficientmatiere_avec_option", table_name="coefficientmatiereetablissement")
    op.drop_index("ix_coefficientmatiereetablissement_matiere_id", table_name="coefficientmatiereetablissement")
    op.drop_index("ix_coefficientmatiereetablissement_option_id", table_name="coefficientmatiereetablissement")
    op.drop_index("ix_coefficientmatiereetablissement_niveau_id", table_name="coefficientmatiereetablissement")
    op.drop_index("ix_coefficientmatiereetablissement_parametres_id", table_name="coefficientmatiereetablissement")
    op.drop_table("coefficientmatiereetablissement")

    op.drop_index("ix_parametresacademiques_etablissement_actif", table_name="parametresacademiquesetablissement")
    op.drop_index("ix_parametresacademiquesetablissement_est_actif", table_name="parametresacademiquesetablissement")
    op.drop_index("ix_parametresacademiquesetablissement_annee_scolaire", table_name="parametresacademiquesetablissement")
    op.drop_index("ix_parametresacademiquesetablissement_etablissement_id", table_name="parametresacademiquesetablissement")
    op.drop_table("parametresacademiquesetablissement")
