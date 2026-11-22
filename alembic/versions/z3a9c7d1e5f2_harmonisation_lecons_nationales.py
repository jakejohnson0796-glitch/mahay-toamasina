"""Ajoute le référentiel des leçons nationales et les analyses comparatives."""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "z3a9c7d1e5f2"
down_revision: Union[str, Sequence[str], None] = "y8f4c2a6d1b9"
branch_labels = None
depends_on = None

FK_TACHE_ANALYSE_COMPARATIVE_LECON = "fk_tacheia_analyse_comparative_lecon"


def upgrade() -> None:
    op.create_table(
        "leconreferentielle",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("programme_matiere_id", sa.Integer(), sa.ForeignKey("programmematierescolaire.id"), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("chapitre", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("titre", sa.String(length=240), nullable=False),
        sa.Column("objectifs_pedagogiques", sa.String(length=5000), nullable=False, server_default=""),
        sa.Column("source_officielle", sa.String(length=1200), nullable=False),
        sa.Column("reference_source", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("statut_validation", sa.String(length=20), nullable=False, server_default="a_verifier"),
        sa.Column("cree_par_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=False),
        sa.Column("valide_par_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=True),
        sa.Column("date_creation", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("date_validation", sa.DateTime(), nullable=True),
        sa.Column("motif_validation", sa.String(length=2000), nullable=False, server_default=""),
        sa.Column("statut_publication", sa.String(length=20), nullable=False, server_default="non_publie"),
        sa.Column("contenu_publie", sa.String(length=100000), nullable=False, server_default=""),
        sa.Column("version_publiee", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("date_publication", sa.DateTime(), nullable=True),
        sa.Column("publie_par_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=True),
        sa.UniqueConstraint("programme_matiere_id", "code", name="uq_leconreferentielle_programme_code"),
        sa.CheckConstraint("statut_validation IN ('a_verifier', 'verifiee', 'archivee')", name="ck_leconreferentielle_statut_validation"),
        sa.CheckConstraint("statut_publication IN ('non_publie', 'publie')", name="ck_leconreferentielle_statut_publication"),
        sa.CheckConstraint("version_publiee >= 0", name="ck_leconreferentielle_version_publiee"),
    )
    op.create_index("ix_leconreferentielle_programme_matiere_id", "leconreferentielle", ["programme_matiere_id"])
    op.create_index("ix_leconreferentielle_statut_validation", "leconreferentielle", ["statut_validation"])
    op.create_index("ix_leconreferentielle_date_creation", "leconreferentielle", ["date_creation"])
    op.create_index("ix_leconreferentielle_statut_publication", "leconreferentielle", ["statut_publication"])
    op.create_index("ix_leconreferentielle_programme_statut", "leconreferentielle", ["programme_matiere_id", "statut_validation"])

    op.create_table(
        "contributionlecon",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("lecon_id", sa.Integer(), sa.ForeignKey("leconreferentielle.id"), nullable=False),
        sa.Column("auteur_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=False),
        sa.Column("titre", sa.String(length=180), nullable=False),
        sa.Column("contenu", sa.String(length=12000), nullable=False),
        sa.Column("source_reference", sa.String(length=2000), nullable=False),
        sa.Column("justification", sa.String(length=5000), nullable=False),
        sa.Column("impact_pedagogique", sa.String(length=3000), nullable=False),
        sa.Column("statut", sa.String(length=20), nullable=False, server_default="soumise"),
        sa.Column("date_creation", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("traite_par_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=True),
        sa.Column("date_traitement", sa.DateTime(), nullable=True),
        sa.Column("motif_decision", sa.String(length=3000), nullable=False, server_default=""),
        sa.CheckConstraint("statut IN ('soumise', 'retenue', 'refusee')", name="ck_contributionlecon_statut"),
    )
    op.create_index("ix_contributionlecon_lecon_id", "contributionlecon", ["lecon_id"])
    op.create_index("ix_contributionlecon_auteur_id", "contributionlecon", ["auteur_id"])
    op.create_index("ix_contributionlecon_statut", "contributionlecon", ["statut"])
    op.create_index("ix_contributionlecon_date_creation", "contributionlecon", ["date_creation"])
    op.create_index("ix_contributionlecon_lecon_statut_date", "contributionlecon", ["lecon_id", "statut", "date_creation"])

    op.create_table(
        "analysecomparativelecon",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("lecon_id", sa.Integer(), sa.ForeignKey("leconreferentielle.id"), nullable=False),
        sa.Column("contributions_ids_json", sa.String(length=2000), nullable=False, server_default="[]"),
        sa.Column("resultat_json", sa.String(length=60000), nullable=False, server_default="{}"),
        sa.Column("modele", sa.String(length=120), nullable=False),
        sa.Column("statut", sa.String(length=20), nullable=False, server_default="en_attente"),
        sa.Column("cree_par_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=False),
        sa.Column("date_creation", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.CheckConstraint("statut IN ('en_attente', 'en_cours', 'terminee', 'a_revoir', 'echouee')", name="ck_analysecomparativelecon_statut"),
    )
    op.create_index("ix_analysecomparativelecon_lecon_id", "analysecomparativelecon", ["lecon_id"])
    op.create_index("ix_analysecomparativelecon_statut", "analysecomparativelecon", ["statut"])
    op.create_index("ix_analysecomparativelecon_cree_par_id", "analysecomparativelecon", ["cree_par_id"])
    op.create_index("ix_analysecomparativelecon_date_creation", "analysecomparativelecon", ["date_creation"])
    op.create_index("ix_analysecomparativelecon_lecon_date", "analysecomparativelecon", ["lecon_id", "date_creation"])

    op.create_table(
        "versioncoursharmoniselecon",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("lecon_id", sa.Integer(), sa.ForeignKey("leconreferentielle.id"), nullable=False),
        sa.Column("numero_version", sa.Integer(), nullable=False),
        sa.Column("contenu", sa.String(length=100000), nullable=False),
        sa.Column("analyse_id", sa.Integer(), sa.ForeignKey("analysecomparativelecon.id"), nullable=True),
        sa.Column("contributions_ids_json", sa.String(length=2000), nullable=False, server_default="[]"),
        sa.Column("publie_par_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=False),
        sa.Column("motif_validation", sa.String(length=3000), nullable=False),
        sa.Column("date_publication", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("lecon_id", "numero_version", name="uq_versioncoursharmonise_lecon_numero"),
        sa.CheckConstraint("numero_version >= 1", name="ck_versioncoursharmonise_numero"),
    )
    op.create_index("ix_versioncoursharmoniselecon_lecon_id", "versioncoursharmoniselecon", ["lecon_id"])
    op.create_index("ix_versioncoursharmoniselecon_analyse_id", "versioncoursharmoniselecon", ["analyse_id"])
    op.create_index("ix_versioncoursharmoniselecon_publie_par_id", "versioncoursharmoniselecon", ["publie_par_id"])
    op.create_index("ix_versioncoursharmoniselecon_date_publication", "versioncoursharmoniselecon", ["date_publication"])
    op.create_index("ix_versioncoursharmonise_lecon_publication", "versioncoursharmoniselecon", ["lecon_id", "date_publication"])

    # L'analyse comparative est une tâche durable ; Redis reste un accélérateur.
    # SQLite cannot ALTER TABLE ADD CONSTRAINT. Add the plain column and
    # the explicitly named FK separately, following the established tacheia
    # migration pattern. Batch mode preserves the existing SQLite schema.
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("tacheia", recreate="always") as batch_op:
            batch_op.add_column(
                sa.Column("analyse_comparative_lecon_id", sa.Integer(), nullable=True)
            )
            batch_op.create_foreign_key(
                FK_TACHE_ANALYSE_COMPARATIVE_LECON,
                "analysecomparativelecon",
                ["analyse_comparative_lecon_id"],
                ["id"],
            )
    else:
        op.add_column(
            "tacheia",
            sa.Column("analyse_comparative_lecon_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            FK_TACHE_ANALYSE_COMPARATIVE_LECON,
            "tacheia",
            "analysecomparativelecon",
            ["analyse_comparative_lecon_id"],
            ["id"],
        )
    op.create_index("ix_tacheia_analyse_comparative_lecon_id", "tacheia", ["analyse_comparative_lecon_id"])
    op.create_index(
        "uq_tache_ia_type_analyse_comparative_lecon",
        "tacheia",
        ["type_tache", "analyse_comparative_lecon_id"],
        unique=True,
    )

    # Les objets de travail ne doivent pas être consultables directement
    # via le Data API Supabase : seul le backend applicatif les utilise.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        tables = (
            "leconreferentielle",
            "contributionlecon",
            "analysecomparativelecon",
            "versioncoursharmoniselecon",
        )
        roles = bind.execute(
            sa.text(
                "SELECT rolname FROM pg_roles "
                "WHERE rolname IN ('anon', 'authenticated')"
            )
        ).scalars().all()
        quote = bind.dialect.identifier_preparer.quote
        for table in tables:
            bind.exec_driver_sql(
                f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY"
            )
            bind.exec_driver_sql(
                f"REVOKE ALL PRIVILEGES ON TABLE public.{table} FROM PUBLIC"
            )
            for role in roles:
                if role in {"anon", "authenticated"}:
                    bind.exec_driver_sql(
                        f"REVOKE ALL PRIVILEGES ON TABLE public.{table} FROM "
                        + quote(role)
                    )

    # Le contenu et l'attribution des contributions deviennent immuables
    # après soumission. L'administration ne peut modifier que le statut et
    # les champs de décision, jamais réécrire la contribution d'origine.
    if bind.dialect.name == "postgresql":
        bind.exec_driver_sql(
            """
            CREATE OR REPLACE FUNCTION public.proteger_contribution_lecon()
            RETURNS trigger LANGUAGE plpgsql AS $contribution$
            BEGIN
                IF TG_OP = 'TRUNCATE' THEN
                    RAISE EXCEPTION 'Les contributions pédagogiques ne peuvent pas être purgées';
                ELSIF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION 'Les contributions pédagogiques ne peuvent pas être supprimées';
                END IF;
                IF ROW(
                    NEW.lecon_id, NEW.auteur_id, NEW.titre, NEW.contenu,
                    NEW.source_reference, NEW.justification,
                    NEW.impact_pedagogique, NEW.date_creation
                ) IS DISTINCT FROM ROW(
                    OLD.lecon_id, OLD.auteur_id, OLD.titre, OLD.contenu,
                    OLD.source_reference, OLD.justification,
                    OLD.impact_pedagogique, OLD.date_creation
                ) THEN
                    RAISE EXCEPTION 'Le contenu original de la contribution est immuable';
                END IF;
                RETURN NEW;
            END;
            $contribution$
            """
        )
        bind.exec_driver_sql(
            "CREATE TRIGGER trg_contributionlecon_immutable "
            "BEFORE UPDATE OR DELETE ON public.contributionlecon "
            "FOR EACH ROW EXECUTE FUNCTION public.proteger_contribution_lecon()"
        )
        bind.exec_driver_sql(
            "CREATE TRIGGER trg_contributionlecon_no_truncate BEFORE TRUNCATE "
            "ON public.contributionlecon FOR EACH STATEMENT "
            "EXECUTE FUNCTION public.proteger_contribution_lecon()"
        )
    elif bind.dialect.name == "sqlite":
        bind.exec_driver_sql(
            """
            CREATE TRIGGER trg_contributionlecon_immutable
            BEFORE UPDATE OF lecon_id, auteur_id, titre, contenu, source_reference,
                             justification, impact_pedagogique, date_creation
            ON contributionlecon
            BEGIN
                SELECT RAISE(ABORT, 'Le contenu original d'une contribution est immuable');
            END
            """
        )
        bind.exec_driver_sql(
            """
            CREATE TRIGGER trg_contributionlecon_no_delete
            BEFORE DELETE ON contributionlecon
            BEGIN
                SELECT RAISE(ABORT, 'Les contributions pédagogiques ne peuvent pas être supprimées');
            END
            """
        )

    # Les versions publiées sont append-only : elles ne peuvent pas être
    # réécrites ou purgées silencieusement, même par une requête SQL.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.exec_driver_sql(
            """
            CREATE OR REPLACE FUNCTION public.proteger_version_cours_harmonise()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'Les versions publiées des cours harmonisés sont en lecture seule';
            END;
            $$
            """
        )
        for trigger, event in (
            ("trg_versioncours_no_update", "UPDATE"),
            ("trg_versioncours_no_delete", "DELETE"),
        ):
            bind.exec_driver_sql(
                f"CREATE TRIGGER {trigger} BEFORE {event} ON public.versioncoursharmoniselecon "
                "FOR EACH ROW EXECUTE FUNCTION public.proteger_version_cours_harmonise()"
            )
        bind.exec_driver_sql(
            "CREATE TRIGGER trg_versioncours_no_truncate BEFORE TRUNCATE "
            "ON public.versioncoursharmoniselecon FOR EACH STATEMENT "
            "EXECUTE FUNCTION public.proteger_version_cours_harmonise()"
        )
    elif bind.dialect.name == "sqlite":
        bind.exec_driver_sql(
            """
            CREATE TRIGGER trg_versioncours_no_update
            BEFORE UPDATE ON versioncoursharmoniselecon
            BEGIN
                SELECT RAISE(ABORT, 'Les versions publiées sont en lecture seule');
            END
            """
        )
        bind.exec_driver_sql(
            """
            CREATE TRIGGER trg_versioncours_no_delete
            BEFORE DELETE ON versioncoursharmoniselecon
            BEGIN
                SELECT RAISE(ABORT, 'Les versions publiées sont en lecture seule');
            END
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.exec_driver_sql("DROP TRIGGER IF EXISTS trg_contributionlecon_immutable ON public.contributionlecon")
        bind.exec_driver_sql("DROP TRIGGER IF EXISTS trg_contributionlecon_no_truncate ON public.contributionlecon")
        bind.exec_driver_sql("DROP FUNCTION IF EXISTS public.proteger_contribution_lecon()")
        bind.exec_driver_sql("DROP TRIGGER IF EXISTS trg_versioncours_no_update ON public.versioncoursharmoniselecon")
        bind.exec_driver_sql("DROP TRIGGER IF EXISTS trg_versioncours_no_delete ON public.versioncoursharmoniselecon")
        bind.exec_driver_sql("DROP TRIGGER IF EXISTS trg_versioncours_no_truncate ON public.versioncoursharmoniselecon")
        bind.exec_driver_sql("DROP FUNCTION IF EXISTS public.proteger_version_cours_harmonise()")
    elif bind.dialect.name == "sqlite":
        bind.exec_driver_sql("DROP TRIGGER IF EXISTS trg_contributionlecon_immutable")
        bind.exec_driver_sql("DROP TRIGGER IF EXISTS trg_contributionlecon_no_delete")
        bind.exec_driver_sql("DROP TRIGGER IF EXISTS trg_versioncours_no_update")
        bind.exec_driver_sql("DROP TRIGGER IF EXISTS trg_versioncours_no_delete")

    op.drop_index("uq_tache_ia_type_analyse_comparative_lecon", table_name="tacheia")
    op.drop_index("ix_tacheia_analyse_comparative_lecon_id", table_name="tacheia")
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("tacheia", recreate="always") as batch_op:
            batch_op.drop_constraint(
                FK_TACHE_ANALYSE_COMPARATIVE_LECON,
                type_="foreignkey",
            )
            batch_op.drop_column("analyse_comparative_lecon_id")
    else:
        op.drop_constraint(
            FK_TACHE_ANALYSE_COMPARATIVE_LECON,
            "tacheia",
            type_="foreignkey",
        )
        op.drop_column("tacheia", "analyse_comparative_lecon_id")

    for name in (
        "ix_versioncoursharmonise_lecon_publication",
        "ix_versioncoursharmoniselecon_date_publication",
        "ix_versioncoursharmoniselecon_publie_par_id",
        "ix_versioncoursharmoniselecon_analyse_id",
        "ix_versioncoursharmoniselecon_lecon_id",
    ):
        op.drop_index(name, table_name="versioncoursharmoniselecon")
    op.drop_table("versioncoursharmoniselecon")

    for name in (
        "ix_analysecomparativelecon_lecon_date",
        "ix_analysecomparativelecon_date_creation",
        "ix_analysecomparativelecon_cree_par_id",
        "ix_analysecomparativelecon_statut",
        "ix_analysecomparativelecon_lecon_id",
    ):
        op.drop_index(name, table_name="analysecomparativelecon")
    op.drop_table("analysecomparativelecon")

    for name in (
        "ix_contributionlecon_lecon_statut_date",
        "ix_contributionlecon_date_creation",
        "ix_contributionlecon_statut",
        "ix_contributionlecon_auteur_id",
        "ix_contributionlecon_lecon_id",
    ):
        op.drop_index(name, table_name="contributionlecon")
    op.drop_table("contributionlecon")

    for name in (
        "ix_leconreferentielle_programme_statut",
        "ix_leconreferentielle_statut_publication",
        "ix_leconreferentielle_date_creation",
        "ix_leconreferentielle_statut_validation",
        "ix_leconreferentielle_programme_matiere_id",
    ):
        op.drop_index(name, table_name="leconreferentielle")
    op.drop_table("leconreferentielle")
