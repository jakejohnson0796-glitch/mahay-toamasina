"""Ajoute un journal d'audit append-only pour les paramètres pédagogiques."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "y8f4c2a6d1b9"
down_revision: Union[str, Sequence[str], None] = "x7e2a4c9b1d5"
branch_labels = None
depends_on = None


_TABLE = "parametresacademiquesevenement"
_TRIGGER_UPDATE = "trg_parametresacademiquesevenement_no_update"
_TRIGGER_DELETE = "trg_parametresacademiquesevenement_no_delete"
_FUNCTION = "public.proteger_journal_parametres_academiques"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "etablissement_id",
            sa.Integer(),
            sa.ForeignKey("etablissementscolaire.id"),
            nullable=False,
        ),
        sa.Column("annee_scolaire", sa.String(length=9), nullable=False),
        sa.Column(
            "acteur_id",
            sa.Integer(),
            sa.ForeignKey("utilisateur.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("acteur_nom", sa.String(length=200), nullable=False),
        sa.Column("action", sa.String(length=24), nullable=False),
        sa.Column("entite_type", sa.String(length=32), nullable=False),
        sa.Column("entite_id", sa.Integer(), nullable=True),
        sa.Column("details_json", sa.String(), nullable=False, server_default="{}"),
        sa.Column(
            "date_evenement",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.CheckConstraint(
            "action IN ('creation', 'modification', 'activation', 'desactivation', 'suppression')",
            name="ck_parametresacademiquesevenement_action",
        ),
    )
    op.create_index(
        "ix_parametresacademiquesevenement_etablissement_id",
        _TABLE,
        ["etablissement_id"],
    )
    op.create_index(
        "ix_parametresacademiquesevenement_annee_scolaire",
        _TABLE,
        ["annee_scolaire"],
    )
    op.create_index(
        "ix_parametresacademiquesevenement_acteur_id",
        _TABLE,
        ["acteur_id"],
    )
    op.create_index(
        "ix_parametresacademiquesevenement_action",
        _TABLE,
        ["action"],
    )
    op.create_index(
        "ix_parametresacademiquesevenement_date_evenement",
        _TABLE,
        ["date_evenement"],
    )
    op.create_index(
        "ix_parametresacademiquesevenement_etab_annee_date",
        _TABLE,
        ["etablissement_id", "annee_scolaire", "date_evenement"],
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.exec_driver_sql(
            f"ALTER TABLE public.{_TABLE} ENABLE ROW LEVEL SECURITY"
        )
        bind.exec_driver_sql(
            f"REVOKE ALL PRIVILEGES ON TABLE public.{_TABLE} FROM PUBLIC"
        )
        roles = bind.execute(
            sa.text(
                "SELECT rolname FROM pg_roles "
                "WHERE rolname IN ('anon', 'authenticated')"
            )
        ).scalars().all()
        quote = bind.dialect.identifier_preparer.quote
        for role in roles:
            if role in {"anon", "authenticated"}:
                bind.exec_driver_sql(
                    f"REVOKE ALL PRIVILEGES ON TABLE public.{_TABLE} FROM "
                    + quote(role)
                )
        bind.exec_driver_sql(
            f"""
            CREATE OR REPLACE FUNCTION {_FUNCTION}()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION
                    'Le journal d audit des paramètres académiques est en lecture seule';
            END;
            $$
            """
        )
        bind.exec_driver_sql(
            f"""
            CREATE TRIGGER {_TRIGGER_UPDATE}
            BEFORE UPDATE ON public.{_TABLE}
            FOR EACH ROW EXECUTE FUNCTION {_FUNCTION}()
            """
        )
        bind.exec_driver_sql(
            f"""
            CREATE TRIGGER {_TRIGGER_DELETE}
            BEFORE DELETE ON public.{_TABLE}
            FOR EACH ROW EXECUTE FUNCTION {_FUNCTION}()
            """
        )
        bind.exec_driver_sql(
            f"""
            CREATE TRIGGER trg_parametresacademiquesevenement_no_truncate
            BEFORE TRUNCATE ON public.{_TABLE}
            FOR EACH STATEMENT EXECUTE FUNCTION {_FUNCTION}()
            """
        )
    elif bind.dialect.name == "sqlite":
        bind.exec_driver_sql(
            f"""
            CREATE TRIGGER {_TRIGGER_UPDATE}
            BEFORE UPDATE ON {_TABLE}
            BEGIN
                SELECT RAISE(ABORT, 'Le journal d audit est en lecture seule');
            END
            """
        )
        bind.exec_driver_sql(
            f"""
            CREATE TRIGGER {_TRIGGER_DELETE}
            BEFORE DELETE ON {_TABLE}
            BEGIN
                SELECT RAISE(ABORT, 'Le journal d audit est en lecture seule');
            END
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.exec_driver_sql(
            f"DROP TRIGGER IF EXISTS {_TRIGGER_UPDATE} ON public.{_TABLE}"
        )
        bind.exec_driver_sql(
            f"DROP TRIGGER IF EXISTS {_TRIGGER_DELETE} ON public.{_TABLE}"
        )
        bind.exec_driver_sql(
            f"DROP TRIGGER IF EXISTS trg_parametresacademiquesevenement_no_truncate ON public.{_TABLE}"
        )
        bind.exec_driver_sql(f"DROP FUNCTION IF EXISTS {_FUNCTION}()")
    elif bind.dialect.name == "sqlite":
        bind.exec_driver_sql(f"DROP TRIGGER IF EXISTS {_TRIGGER_UPDATE}")
        bind.exec_driver_sql(f"DROP TRIGGER IF EXISTS {_TRIGGER_DELETE}")

    op.drop_index(
        "ix_parametresacademiquesevenement_etab_annee_date",
        table_name=_TABLE,
    )
    op.drop_index(
        "ix_parametresacademiquesevenement_date_evenement",
        table_name=_TABLE,
    )
    op.drop_index(
        "ix_parametresacademiquesevenement_action",
        table_name=_TABLE,
    )
    op.drop_index(
        "ix_parametresacademiquesevenement_acteur_id",
        table_name=_TABLE,
    )
    op.drop_index(
        "ix_parametresacademiquesevenement_annee_scolaire",
        table_name=_TABLE,
    )
    op.drop_index(
        "ix_parametresacademiquesevenement_etablissement_id",
        table_name=_TABLE,
    )
    op.drop_table(_TABLE)
