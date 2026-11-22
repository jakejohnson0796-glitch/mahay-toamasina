"""Ajoute le référentiel versionné des programmes officiels EP/FRP."""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a4b8c2d6e9f1"
down_revision: Union[str, Sequence[str], None] = "z3a9c7d1e5f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "programmeofficielscolaire",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("intitule", sa.String(length=250), nullable=False),
        sa.Column("organisme_emetteur", sa.String(length=180), nullable=False),
        sa.Column("type_document", sa.String(length=12), nullable=False),
        sa.Column("annee_publication", sa.Integer(), nullable=True),
        sa.Column("annee_scolaire", sa.String(length=20), nullable=True),
        sa.Column("version_officielle", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("programme_matiere_id", sa.Integer(), sa.ForeignKey("programmematierescolaire.id"), nullable=False),
        sa.Column("source_url", sa.String(length=1200), nullable=True),
        sa.Column("reference_source", sa.String(length=1200), nullable=False, server_default=""),
        sa.Column("nom_fichier_original", sa.String(length=255), nullable=False),
        sa.Column("chemin_fichier", sa.String(length=1200), nullable=False),
        sa.Column("type_mime", sa.String(length=120), nullable=False),
        sa.Column("empreinte_sha256", sa.String(length=64), nullable=False),
        sa.Column("taille_octets", sa.Integer(), nullable=False),
        sa.Column("texte_extrait", sa.Text(), nullable=False, server_default=""),
        sa.Column("statut_extraction", sa.String(length=20), nullable=False, server_default="en_attente"),
        sa.Column("nombre_caracteres_extraits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("statut_validation", sa.String(length=20), nullable=False, server_default="a_verifier"),
        sa.Column("motif_validation", sa.String(length=4000), nullable=False, server_default=""),
        sa.Column("version_precedente_id", sa.Integer(), sa.ForeignKey("programmeofficielscolaire.id"), nullable=True),
        sa.Column("importe_par_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=False),
        sa.Column("verifie_par_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=True),
        sa.Column("date_import", sa.DateTime(), nullable=False),
        sa.Column("date_verification", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("code", name="uq_programmeofficiel_code"),
        sa.CheckConstraint(
            "type_document IN ('EP', 'FRP', 'AUTRE')",
            name="ck_programmeofficiel_type_document",
        ),
        sa.CheckConstraint(
            "statut_extraction IN ('en_attente', 'extrait', 'partiel', 'echec')",
            name="ck_programmeofficiel_statut_extraction",
        ),
        sa.CheckConstraint(
            "statut_validation IN ('a_verifier', 'verifie', 'rejete', 'archive')",
            name="ck_programmeofficiel_statut_validation",
        ),
        sa.CheckConstraint("taille_octets > 0", name="ck_programmeofficiel_taille"),
    )
    for name, columns in (
        ("ix_programmeofficielscolaire_code", ["code"]),
        ("ix_programmeofficielscolaire_type_document", ["type_document"]),
        ("ix_programmeofficielscolaire_annee_publication", ["annee_publication"]),
        ("ix_programmeofficielscolaire_annee_scolaire", ["annee_scolaire"]),
        ("ix_programmeofficielscolaire_empreinte_sha256", ["empreinte_sha256"]),
        ("ix_programmeofficielscolaire_statut_extraction", ["statut_extraction"]),
        ("ix_programmeofficielscolaire_statut_validation", ["statut_validation"]),
        ("ix_programmeofficielscolaire_version_precedente_id", ["version_precedente_id"]),
        ("ix_programmeofficielscolaire_importe_par_id", ["importe_par_id"]),
        ("ix_programmeofficielscolaire_verifie_par_id", ["verifie_par_id"]),
        ("ix_programmeofficielscolaire_date_import", ["date_import"]),
        ("ix_programmeofficiel_matiere_validation_date", ["programme_matiere_id", "statut_validation", "date_import"]),
    ):
        op.create_index(name, "programmeofficielscolaire", columns, unique=False)

    op.create_table(
        "elementprogrammeofficiel",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("programme_id", sa.Integer(), sa.ForeignKey("programmeofficielscolaire.id"), nullable=False),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("elementprogrammeofficiel.id"), nullable=True),
        sa.Column("lecon_referentielle_id", sa.Integer(), sa.ForeignKey("leconreferentielle.id"), nullable=True),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("type_element", sa.String(length=20), nullable=False),
        sa.Column("titre", sa.String(length=240), nullable=False),
        sa.Column("contenu", sa.Text(), nullable=False, server_default=""),
        sa.Column("ordre", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("page_debut", sa.Integer(), nullable=True),
        sa.Column("statut_validation", sa.String(length=20), nullable=False, server_default="a_verifier"),
        sa.Column("motif_validation", sa.String(length=2000), nullable=False, server_default=""),
        sa.Column("valide_par_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=True),
        sa.Column("date_validation", sa.DateTime(), nullable=True),
        sa.Column("date_creation", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("programme_id", "code", name="uq_elementprogramme_programme_code"),
        sa.CheckConstraint(
            "type_element IN ('chapitre', 'lecon', 'rubrique', 'objectif')",
            name="ck_elementprogramme_type",
        ),
        sa.CheckConstraint(
            "statut_validation IN ('a_verifier', 'verifie', 'rejete')",
            name="ck_elementprogramme_statut",
        ),
    )
    for name, columns in (
        ("ix_elementprogrammeofficiel_programme_id", ["programme_id"]),
        ("ix_elementprogrammeofficiel_parent_id", ["parent_id"]),
        ("ix_elementprogrammeofficiel_lecon_referentielle_id", ["lecon_referentielle_id"]),
        ("ix_elementprogrammeofficiel_type_element", ["type_element"]),
        ("ix_elementprogrammeofficiel_statut_validation", ["statut_validation"]),
        ("ix_elementprogrammeofficiel_valide_par_id", ["valide_par_id"]),
        ("ix_elementprogrammeofficiel_date_creation", ["date_creation"]),
        ("ix_elementprogramme_programme_statut_ordre", ["programme_id", "statut_validation", "ordre"]),
    ):
        op.create_index(name, "elementprogrammeofficiel", columns, unique=False)

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in ("programmeofficielscolaire", "elementprogrammeofficiel"):
            bind.exec_driver_sql(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
            bind.exec_driver_sql(f"REVOKE ALL PRIVILEGES ON TABLE public.{table} FROM PUBLIC")
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
                        f"REVOKE ALL PRIVILEGES ON TABLE public.{table} FROM " + quote(role)
                    )

        bind.exec_driver_sql(
            """
            CREATE OR REPLACE FUNCTION public.proteger_programme_officiel()
            RETURNS trigger LANGUAGE plpgsql AS $programme$
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION 'Les documents officiels importés sont conservés et archivés, jamais supprimés';
                END IF;
                IF OLD.statut_validation = 'verifie' AND ROW(
                    NEW.code, NEW.intitule, NEW.organisme_emetteur, NEW.type_document,
                    NEW.annee_publication, NEW.annee_scolaire, NEW.version_officielle,
                    NEW.programme_matiere_id, NEW.source_url, NEW.reference_source,
                    NEW.nom_fichier_original, NEW.chemin_fichier, NEW.type_mime,
                    NEW.empreinte_sha256, NEW.taille_octets, NEW.texte_extrait,
                    NEW.version_precedente_id, NEW.importe_par_id, NEW.date_import
                ) IS DISTINCT FROM ROW(
                    OLD.code, OLD.intitule, OLD.organisme_emetteur, OLD.type_document,
                    OLD.annee_publication, OLD.annee_scolaire, OLD.version_officielle,
                    OLD.programme_matiere_id, OLD.source_url, OLD.reference_source,
                    OLD.nom_fichier_original, OLD.chemin_fichier, OLD.type_mime,
                    OLD.empreinte_sha256, OLD.taille_octets, OLD.texte_extrait,
                    OLD.version_precedente_id, OLD.importe_par_id, OLD.date_import
                ) THEN
                    RAISE EXCEPTION 'La source officielle vérifiée est immuable ; importer une nouvelle version';
                END IF;
                RETURN NEW;
            END;
            $programme$
            """
        )
        bind.exec_driver_sql(
            "CREATE TRIGGER trg_programmeofficiel_immutable "
            "BEFORE UPDATE OR DELETE ON public.programmeofficielscolaire "
            "FOR EACH ROW EXECUTE FUNCTION public.proteger_programme_officiel()"
        )
        bind.exec_driver_sql(
            """
            CREATE OR REPLACE FUNCTION public.proteger_element_programme_officiel()
            RETURNS trigger LANGUAGE plpgsql AS $element$
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION 'Les éléments du programme sont conservés dans l’historique';
                END IF;
                IF OLD.statut_validation = 'verifie' AND ROW(
                    NEW.programme_id, NEW.parent_id, NEW.lecon_referentielle_id,
                    NEW.code, NEW.type_element, NEW.titre, NEW.contenu, NEW.ordre,
                    NEW.page_debut, NEW.motif_validation, NEW.valide_par_id,
                    NEW.date_validation
                ) IS DISTINCT FROM ROW(
                    OLD.programme_id, OLD.parent_id, OLD.lecon_referentielle_id,
                    OLD.code, OLD.type_element, OLD.titre, OLD.contenu, OLD.ordre,
                    OLD.page_debut, OLD.motif_validation, OLD.valide_par_id,
                    OLD.date_validation
                ) THEN
                    RAISE EXCEPTION 'Un élément vérifié est immuable ; créer une nouvelle version du programme';
                END IF;
                RETURN NEW;
            END;
            $element$
            """
        )
        bind.exec_driver_sql(
            "CREATE TRIGGER trg_elementprogramme_immutable "
            "BEFORE UPDATE OR DELETE ON public.elementprogrammeofficiel "
            "FOR EACH ROW EXECUTE FUNCTION public.proteger_element_programme_officiel()"
        )
    elif bind.dialect.name == "sqlite":
        bind.exec_driver_sql(
            """
            CREATE TRIGGER trg_programmeofficiel_immutable
            BEFORE UPDATE OF code, intitule, organisme_emetteur, type_document,
                annee_publication, annee_scolaire, version_officielle,
                programme_matiere_id, source_url, reference_source,
                nom_fichier_original, chemin_fichier, type_mime,
                empreinte_sha256, taille_octets, texte_extrait,
                version_precedente_id, importe_par_id, date_import
            ON programmeofficielscolaire
            WHEN OLD.statut_validation = 'verifie'
            BEGIN
                SELECT RAISE(ABORT, 'La source officielle vérifiée est immuable');
            END
            """
        )
        bind.exec_driver_sql(
            """
            CREATE TRIGGER trg_programmeofficiel_no_delete
            BEFORE DELETE ON programmeofficielscolaire
            BEGIN
                SELECT RAISE(ABORT, 'Les documents importés doivent être archivés');
            END
            """
        )
        bind.exec_driver_sql(
            """
            CREATE TRIGGER trg_elementprogramme_immutable
            BEFORE UPDATE OF programme_id, parent_id, lecon_referentielle_id,
                code, type_element, titre, contenu, ordre, page_debut,
                motif_validation, valide_par_id, date_validation
            ON elementprogrammeofficiel
            WHEN OLD.statut_validation = 'verifie'
            BEGIN
                SELECT RAISE(ABORT, 'Un élément vérifié est immuable');
            END
            """
        )
        bind.exec_driver_sql(
            """
            CREATE TRIGGER trg_elementprogramme_no_delete
            BEFORE DELETE ON elementprogrammeofficiel
            BEGIN
                SELECT RAISE(ABORT, 'Les éléments du programme doivent être conservés');
            END
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.exec_driver_sql("DROP TRIGGER IF EXISTS trg_programmeofficiel_immutable ON public.programmeofficielscolaire")
        bind.exec_driver_sql("DROP FUNCTION IF EXISTS public.proteger_programme_officiel()")
        bind.exec_driver_sql("DROP TRIGGER IF EXISTS trg_elementprogramme_immutable ON public.elementprogrammeofficiel")
        bind.exec_driver_sql("DROP FUNCTION IF EXISTS public.proteger_element_programme_officiel()")
    elif bind.dialect.name == "sqlite":
        for trigger in (
            "trg_programmeofficiel_immutable",
            "trg_programmeofficiel_no_delete",
            "trg_elementprogramme_immutable",
            "trg_elementprogramme_no_delete",
        ):
            bind.exec_driver_sql(f"DROP TRIGGER IF EXISTS {trigger}")

    for name in (
        "ix_elementprogramme_programme_statut_ordre",
        "ix_elementprogrammeofficiel_date_creation",
        "ix_elementprogrammeofficiel_valide_par_id",
        "ix_elementprogrammeofficiel_statut_validation",
        "ix_elementprogrammeofficiel_type_element",
        "ix_elementprogrammeofficiel_lecon_referentielle_id",
        "ix_elementprogrammeofficiel_parent_id",
        "ix_elementprogrammeofficiel_programme_id",
    ):
        op.drop_index(name, table_name="elementprogrammeofficiel")
    op.drop_table("elementprogrammeofficiel")

    for name in (
        "ix_programmeofficiel_matiere_validation_date",
        "ix_programmeofficielscolaire_date_import",
        "ix_programmeofficielscolaire_verifie_par_id",
        "ix_programmeofficielscolaire_importe_par_id",
        "ix_programmeofficielscolaire_version_precedente_id",
        "ix_programmeofficielscolaire_statut_validation",
        "ix_programmeofficielscolaire_statut_extraction",
        "ix_programmeofficielscolaire_empreinte_sha256",
        "ix_programmeofficielscolaire_annee_scolaire",
        "ix_programmeofficielscolaire_annee_publication",
        "ix_programmeofficielscolaire_type_document",
        "ix_programmeofficielscolaire_code",
    ):
        op.drop_index(name, table_name="programmeofficielscolaire")
    op.drop_table("programmeofficielscolaire")
