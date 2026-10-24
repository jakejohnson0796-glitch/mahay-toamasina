"""Ajoute un référentiel scolaire national versionné sans supprimer le profil universitaire.

Revision ID: c5f7a12e9b31
Revises: a7c9e2f41d60
Create Date: 2026-10-24
"""
from alembic import op
import sqlalchemy as sa


revision = "c5f7a12e9b31"
down_revision = "a7c9e2f41d60"
branch_labels = None
depends_on = None

SOURCE_PROGRAMMES = "https://www.education.gov.mg/repartition-annuelle-du-programme-scolaire/"
SOURCE_LYCEE = "https://www.education.gov.mg/systeme-educatif/lycee/"


def _seed_catalogue_scolaire(conn):
    """Seed idempotent : la version est volontairement marquée partielle.

    Le catalogue initial couvre les classes générales documentées par le MEN.
    Il ne prétend pas recenser toutes les filières techniques/professionnelles,
    ni leur disponibilité dans chaque établissement.
    """
    code = "MEN-programmes-2026-initial"
    row = conn.execute(
        sa.text("SELECT id FROM referentielscolaire WHERE code = :code"),
        {"code": code},
    ).first()
    if row:
        referentiel_id = row[0]
    else:
        conn.execute(
            sa.text(
                "INSERT INTO referentielscolaire "
                "(code, libelle, annee_scolaire, source_officielle, statut, date_creation) "
                "VALUES (:code, :libelle, :annee, :source, 'partiel', CURRENT_TIMESTAMP)"
            ),
            {
                "code": code,
                "libelle": "Programmes scolaires MEN — inventaire général initial",
                "annee": None,
                "source": SOURCE_PROGRAMMES + " | " + SOURCE_LYCEE,
            },
        )
        referentiel_id = conn.execute(
            sa.text("SELECT id FROM referentielscolaire WHERE code = :code"),
            {"code": code},
        ).scalar_one()

    niveaux = [
        ("6E", "6e", "college", 1, SOURCE_PROGRAMMES),
        ("5E", "5e", "college", 2, SOURCE_PROGRAMMES),
        ("4E", "4e", "college", 3, SOURCE_PROGRAMMES),
        ("3E", "3e", "college", 4, SOURCE_PROGRAMMES),
        ("2NDE", "Seconde", "lycee", 5, SOURCE_LYCEE),
        ("1ERE", "Première", "lycee", 6, SOURCE_PROGRAMMES),
        ("TERM", "Terminale", "lycee", 7, SOURCE_PROGRAMMES),
    ]
    for code_niveau, libelle, cycle, ordre, source in niveaux:
        conn.execute(
            sa.text(
                "INSERT INTO niveauscolaire "
                "(referentiel_id, code, libelle, cycle, ordre, est_actif, source_officielle, statut_validation) "
                "SELECT :ref, :code, :libelle, :cycle, :ordre, TRUE, :source, 'verifie' "
                "WHERE NOT EXISTS (SELECT 1 FROM niveauscolaire WHERE referentiel_id=:ref AND code=:code)"
            ),
            {
                "ref": referentiel_id,
                "code": code_niveau,
                "libelle": libelle,
                "cycle": cycle,
                "ordre": ordre,
                "source": source,
            },
        )

    # Ces séries sont publiées dans les pages de programmes du MEN. Une
    # série n'est proposée que pour un niveau auquel la source la rattache.
    series_par_niveau = {
        "2NDE": ["A", "C", "D"],
        "1ERE": ["A", "C", "D", "L", "OSE", "S"],
        "TERM": ["A", "C", "D", "L", "OSE", "S"],
    }
    labels = {
        "A": "Série A",
        "C": "Série C",
        "D": "Série D",
        "L": "Série L",
        "OSE": "Série OSE",
        "S": "Série S",
    }
    for code_niveau, codes_series in series_par_niveau.items():
        niveau_id = conn.execute(
            sa.text(
                "SELECT id FROM niveauscolaire WHERE referentiel_id=:ref AND code=:code"
            ),
            {"ref": referentiel_id, "code": code_niveau},
        ).scalar_one()
        source = SOURCE_LYCEE if code_niveau == "2NDE" else SOURCE_PROGRAMMES
        for code_option in codes_series:
            conn.execute(
                sa.text(
                    "INSERT INTO optionscolaire "
                    "(referentiel_id, niveau_id, code, libelle, type_option, est_active, source_officielle, statut_validation) "
                    "SELECT :ref, :niveau, :code, :libelle, 'serie', TRUE, :source, 'verifie' "
                    "WHERE NOT EXISTS (SELECT 1 FROM optionscolaire WHERE niveau_id=:niveau AND code=:code)"
                ),
                {
                    "ref": referentiel_id,
                    "niveau": niveau_id,
                    "code": code_option,
                    "libelle": labels[code_option],
                    "source": source,
                },
            )


def upgrade():
    op.create_table(
        "referentielscolaire",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("libelle", sa.String(), nullable=False),
        sa.Column("annee_scolaire", sa.String(length=20), nullable=True),
        sa.Column("source_officielle", sa.String(), nullable=False),
        sa.Column("statut", sa.String(length=20), server_default="partiel", nullable=False),
        sa.Column("date_creation", sa.DateTime(), nullable=False),
        sa.Column("date_validation", sa.DateTime(), nullable=True),
        sa.Column("valide_par_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=True),
        sa.UniqueConstraint("code", name="uq_referentielscolaire_code"),
    )
    op.create_index("ix_referentielscolaire_code", "referentielscolaire", ["code"], unique=True)
    op.create_index("ix_referentielscolaire_statut", "referentielscolaire", ["statut"])

    op.create_table(
        "niveauscolaire",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("referentiel_id", sa.Integer(), sa.ForeignKey("referentielscolaire.id"), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("libelle", sa.String(), nullable=False),
        sa.Column("cycle", sa.String(length=20), nullable=False),
        sa.Column("ordre", sa.Integer(), nullable=False),
        sa.Column("est_actif", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("source_officielle", sa.String(), nullable=True),
        sa.Column("statut_validation", sa.String(length=20), server_default="verifie", nullable=False),
        sa.UniqueConstraint("referentiel_id", "code", name="uq_niveauscolaire_referentiel_code"),
    )
    op.create_index("ix_niveauscolaire_referentiel_id", "niveauscolaire", ["referentiel_id"])
    op.create_index("ix_niveauscolaire_code", "niveauscolaire", ["code"])
    op.create_index("ix_niveauscolaire_cycle", "niveauscolaire", ["cycle"])
    op.create_index("ix_niveauscolaire_est_actif", "niveauscolaire", ["est_actif"])
    op.create_index("ix_niveauscolaire_statut_validation", "niveauscolaire", ["statut_validation"])

    op.create_table(
        "optionscolaire",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("referentiel_id", sa.Integer(), sa.ForeignKey("referentielscolaire.id"), nullable=False),
        sa.Column("niveau_id", sa.Integer(), sa.ForeignKey("niveauscolaire.id"), nullable=False),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("libelle", sa.String(), nullable=False),
        sa.Column("type_option", sa.String(length=30), server_default="serie", nullable=False),
        sa.Column("est_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("source_officielle", sa.String(), nullable=True),
        sa.Column("statut_validation", sa.String(length=20), server_default="a_verifier", nullable=False),
        sa.UniqueConstraint("niveau_id", "code", name="uq_optionscolaire_niveau_code"),
    )
    op.create_index("ix_optionscolaire_referentiel_id", "optionscolaire", ["referentiel_id"])
    op.create_index("ix_optionscolaire_niveau_id", "optionscolaire", ["niveau_id"])
    op.create_index("ix_optionscolaire_est_active", "optionscolaire", ["est_active"])
    op.create_index("ix_optionscolaire_statut_validation", "optionscolaire", ["statut_validation"])
    op.create_index("ix_optionscolaire_type_option", "optionscolaire", ["type_option"])

    op.create_table(
        "matierescolaire",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("libelle", sa.String(), nullable=False),
        sa.Column("libelle_malagasy", sa.String(), nullable=True),
        sa.Column("source_officielle", sa.String(), nullable=True),
        sa.Column("statut_validation", sa.String(length=20), server_default="a_verifier", nullable=False),
        sa.Column("est_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.UniqueConstraint("code", name="uq_matierescolaire_code"),
    )
    op.create_index("ix_matierescolaire_code", "matierescolaire", ["code"], unique=True)
    op.create_index("ix_matierescolaire_est_active", "matierescolaire", ["est_active"])
    op.create_index("ix_matierescolaire_statut_validation", "matierescolaire", ["statut_validation"])

    op.create_table(
        "programmematierescolaire",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("referentiel_id", sa.Integer(), sa.ForeignKey("referentielscolaire.id"), nullable=False),
        sa.Column("niveau_id", sa.Integer(), sa.ForeignKey("niveauscolaire.id"), nullable=False),
        sa.Column("option_id", sa.Integer(), sa.ForeignKey("optionscolaire.id"), nullable=True),
        sa.Column("matiere_id", sa.Integer(), sa.ForeignKey("matierescolaire.id"), nullable=False),
        sa.Column("obligatoire", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("source_officielle", sa.String(), nullable=True),
        sa.Column("statut_validation", sa.String(length=20), server_default="a_verifier", nullable=False),
        sa.UniqueConstraint(
            "referentiel_id", "niveau_id", "option_id", "matiere_id",
            name="uq_programmematiere_referentiel_niveau_option_matiere",
        ),
    )
    for column in ("referentiel_id", "niveau_id", "option_id", "matiere_id", "statut_validation"):
        op.create_index(f"ix_programmematierescolaire_{column}", "programmematierescolaire", [column])

    op.create_table(
        "etablissementscolaire",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nom", sa.String(), nullable=False),
        sa.Column("code", sa.String(), nullable=True),
        sa.Column("type_etablissement", sa.String(length=30), server_default="college_lycee", nullable=False),
        sa.Column("secteur", sa.String(length=20), server_default="inconnu", nullable=False),
        sa.Column("region", sa.String(), nullable=True),
        sa.Column("district", sa.String(), nullable=True),
        sa.Column("commune", sa.String(), nullable=True),
        sa.Column("source_officielle", sa.String(), nullable=True),
        sa.Column("est_verifie", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("est_actif", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("date_creation", sa.DateTime(), nullable=False),
        sa.Column("date_maj", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("code", name="uq_etablissementscolaire_code"),
    )
    for column in ("nom", "code", "type_etablissement", "secteur", "region", "district", "commune", "est_verifie", "est_actif"):
        op.create_index(f"ix_etablissementscolaire_{column}", "etablissementscolaire", [column], unique=(column == "code"))

    with op.batch_alter_table("utilisateur") as batch:
        batch.add_column(sa.Column("profil_souhaite", sa.String(length=20), server_default="eleve", nullable=False))
        batch.add_column(sa.Column("cycle_education", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("niveau_scolaire_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("option_scolaire_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("etablissement_scolaire_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("statut_verification_enseignant", sa.String(length=20), server_default="non_concerne", nullable=False))
        batch.add_column(sa.Column("demande_enseignant_le", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("verification_enseignant_le", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("verification_enseignant_par_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("motif_refus_enseignant", sa.String(), nullable=True))
        batch.create_foreign_key("fk_utilisateur_niveau_scolaire", "niveauscolaire", ["niveau_scolaire_id"], ["id"])
        batch.create_foreign_key("fk_utilisateur_option_scolaire", "optionscolaire", ["option_scolaire_id"], ["id"])
        batch.create_foreign_key("fk_utilisateur_etablissement_scolaire", "etablissementscolaire", ["etablissement_scolaire_id"], ["id"])
        batch.create_foreign_key("fk_utilisateur_verification_enseignant", "utilisateur", ["verification_enseignant_par_id"], ["id"])
    for col in ("profil_souhaite", "cycle_education", "niveau_scolaire_id", "option_scolaire_id", "etablissement_scolaire_id", "statut_verification_enseignant"):
        op.create_index(f"ix_utilisateur_{col}", "utilisateur", [col])

    # Preserve existing accounts and accurately mark already-promoted teachers.
    op.execute(sa.text(
        "UPDATE utilisateur SET profil_souhaite='professeur', statut_verification_enseignant='approuve' "
        "WHERE lower(CAST(role AS VARCHAR)) IN ('professeur')"
    ))
    op.execute(sa.text(
        "UPDATE utilisateur SET profil_souhaite='sponsor' "
        "WHERE lower(CAST(role AS VARCHAR)) IN ('sponsor')"
    ))
    op.execute(sa.text(
        "UPDATE utilisateur SET cycle_education='universite' "
        "WHERE universite_id IS NOT NULL AND cycle_education IS NULL"
    ))

    with op.batch_alter_table("document") as batch:
        batch.alter_column("filiere_id", existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column("portee_academique", sa.String(length=20), server_default="universitaire", nullable=False))
        batch.add_column(sa.Column("niveau_scolaire_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("option_scolaire_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("etablissement_scolaire_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("matiere_scolaire_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_document_niveau_scolaire", "niveauscolaire", ["niveau_scolaire_id"], ["id"])
        batch.create_foreign_key("fk_document_option_scolaire", "optionscolaire", ["option_scolaire_id"], ["id"])
        batch.create_foreign_key("fk_document_etablissement_scolaire", "etablissementscolaire", ["etablissement_scolaire_id"], ["id"])
        batch.create_foreign_key("fk_document_matiere_scolaire", "matierescolaire", ["matiere_scolaire_id"], ["id"])
        batch.create_check_constraint(
            "ck_document_portee_academique_cible",
            "(portee_academique = 'universitaire' AND filiere_id IS NOT NULL "
            "AND niveau_scolaire_id IS NULL) OR "
            "(portee_academique = 'scolaire' AND filiere_id IS NULL "
            "AND niveau_scolaire_id IS NOT NULL)",
        )
    op.create_index("ix_document_portee_academique", "document", ["portee_academique"])
    op.create_index("ix_document_niveau_scolaire_id", "document", ["niveau_scolaire_id"])
    op.create_index("ix_document_option_scolaire_id", "document", ["option_scolaire_id"])
    op.create_index("ix_document_etablissement_scolaire_id", "document", ["etablissement_scolaire_id"])
    op.create_index("ix_document_matiere_scolaire_id", "document", ["matiere_scolaire_id"])

    with op.batch_alter_table("cercleetude") as batch:
        batch.add_column(sa.Column("portee_academique", sa.String(length=20), server_default="universitaire", nullable=False))
        batch.add_column(sa.Column("niveau_scolaire_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("option_scolaire_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("etablissement_scolaire_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("matiere_scolaire_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_cercle_niveau_scolaire", "niveauscolaire", ["niveau_scolaire_id"], ["id"])
        batch.create_foreign_key("fk_cercle_option_scolaire", "optionscolaire", ["option_scolaire_id"], ["id"])
        batch.create_foreign_key("fk_cercle_etablissement_scolaire", "etablissementscolaire", ["etablissement_scolaire_id"], ["id"])
        batch.create_foreign_key("fk_cercle_matiere_scolaire", "matierescolaire", ["matiere_scolaire_id"], ["id"])
    for col in ("portee_academique", "niveau_scolaire_id", "option_scolaire_id", "etablissement_scolaire_id", "matiere_scolaire_id"):
        op.create_index(f"ix_cercleetude_{col}", "cercleetude", [col])
    op.create_index(
        "ix_cercle_scolaire_cible_actif",
        "cercleetude",
        [
            "niveau_scolaire_id",
            "option_scolaire_id",
            "etablissement_scolaire_id",
            "matiere_scolaire_id",
        ],
        unique=False,
        postgresql_where=sa.text(
            "portee_academique = 'scolaire' AND niveau_scolaire_id IS NOT NULL"
        ),
        sqlite_where=sa.text(
            "portee_academique = 'scolaire' AND niveau_scolaire_id IS NOT NULL"
        ),
    )

    with op.batch_alter_table("cours") as batch:
        batch.add_column(sa.Column("portee_academique", sa.String(length=20), server_default="universitaire", nullable=False))
        batch.add_column(sa.Column("niveau_scolaire_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("option_scolaire_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("etablissement_scolaire_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("matiere_scolaire_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_cours_niveau_scolaire", "niveauscolaire", ["niveau_scolaire_id"], ["id"])
        batch.create_foreign_key("fk_cours_option_scolaire", "optionscolaire", ["option_scolaire_id"], ["id"])
        batch.create_foreign_key("fk_cours_etablissement_scolaire", "etablissementscolaire", ["etablissement_scolaire_id"], ["id"])
        batch.create_foreign_key("fk_cours_matiere_scolaire", "matierescolaire", ["matiere_scolaire_id"], ["id"])
    for col in ("portee_academique", "niveau_scolaire_id", "option_scolaire_id", "etablissement_scolaire_id", "matiere_scolaire_id"):
        op.create_index(f"ix_cours_{col}", "cours", [col])

    with op.batch_alter_table("demandecreationcercle") as batch:
        batch.add_column(sa.Column("portee_academique", sa.String(length=20), server_default="universitaire", nullable=False))
        batch.add_column(sa.Column("niveau_scolaire_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("option_scolaire_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("etablissement_scolaire_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_demandecercle_niveau_scolaire", "niveauscolaire", ["niveau_scolaire_id"], ["id"])
        batch.create_foreign_key("fk_demandecercle_option_scolaire", "optionscolaire", ["option_scolaire_id"], ["id"])
        batch.create_foreign_key("fk_demandecercle_etablissement_scolaire", "etablissementscolaire", ["etablissement_scolaire_id"], ["id"])
    for col in ("portee_academique", "niveau_scolaire_id", "option_scolaire_id", "etablissement_scolaire_id"):
        op.create_index(f"ix_demandecreationcercle_{col}", "demandecreationcercle", [col])

    with op.batch_alter_table("tentativequiz") as batch:
        batch.add_column(sa.Column("cycle_education", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("niveau_scolaire_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("option_scolaire_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_tentativequiz_niveau_scolaire", "niveauscolaire", ["niveau_scolaire_id"], ["id"])
        batch.create_foreign_key("fk_tentativequiz_option_scolaire", "optionscolaire", ["option_scolaire_id"], ["id"])
    op.create_index("ix_tentativequiz_niveau_scolaire_id", "tentativequiz", ["niveau_scolaire_id"])
    op.create_index("ix_tentativequiz_option_scolaire_id", "tentativequiz", ["option_scolaire_id"])

    # Legacy circles with no academic target are explicitly transversal.
    op.execute(sa.text(
        "UPDATE cercleetude SET portee_academique='transversal' "
        "WHERE mention_id IS NULL AND filiere_id IS NULL AND niveau IS NULL"
    ))

    _seed_catalogue_scolaire(op.get_bind())


def downgrade():
    for col in ("portee_academique", "niveau_scolaire_id", "option_scolaire_id", "etablissement_scolaire_id"):
        op.drop_index(f"ix_demandecreationcercle_{col}", table_name="demandecreationcercle")
    with op.batch_alter_table("demandecreationcercle") as batch:
        for name in ("fk_demandecercle_etablissement_scolaire", "fk_demandecercle_option_scolaire", "fk_demandecercle_niveau_scolaire"):
            batch.drop_constraint(name, type_="foreignkey")
        for col in ("etablissement_scolaire_id", "option_scolaire_id", "niveau_scolaire_id", "portee_academique"):
            batch.drop_column(col)

    with op.batch_alter_table("tentativequiz") as batch:
        batch.drop_constraint("fk_tentativequiz_option_scolaire", type_="foreignkey")
        batch.drop_constraint("fk_tentativequiz_niveau_scolaire", type_="foreignkey")
        batch.drop_column("option_scolaire_id")
        batch.drop_column("niveau_scolaire_id")
        batch.drop_column("cycle_education")
    for col in ("niveau_scolaire_id", "option_scolaire_id"):
        op.drop_index(f"ix_tentativequiz_{col}", table_name="tentativequiz")

    op.drop_index("ix_cercle_scolaire_cible_actif", table_name="cercleetude")
    for table in ("cours", "cercleetude"):
        for col in ("portee_academique", "niveau_scolaire_id", "option_scolaire_id", "etablissement_scolaire_id", "matiere_scolaire_id"):
            op.drop_index(f"ix_{table}_{col}", table_name=table)
        with op.batch_alter_table(table) as batch:
            for col in ("matiere_scolaire_id", "etablissement_scolaire_id", "option_scolaire_id", "niveau_scolaire_id"):
                batch.drop_column(col)
            batch.drop_column("portee_academique")

    for col in ("portee_academique", "niveau_scolaire_id", "option_scolaire_id", "etablissement_scolaire_id", "matiere_scolaire_id"):
        op.drop_index(f"ix_document_{col}", table_name="document")
    with op.batch_alter_table("document") as batch:
        batch.drop_constraint("ck_document_portee_academique_cible", type_="check")
        for name in ("fk_document_matiere_scolaire", "fk_document_etablissement_scolaire", "fk_document_option_scolaire", "fk_document_niveau_scolaire"):
            batch.drop_constraint(name, type_="foreignkey")
        batch.drop_column("matiere_scolaire_id")
        batch.drop_column("etablissement_scolaire_id")
        batch.drop_column("option_scolaire_id")
        batch.drop_column("niveau_scolaire_id")
        batch.drop_column("portee_academique")
        batch.alter_column("filiere_id", existing_type=sa.Integer(), nullable=False)

    for col in ("profil_souhaite", "cycle_education", "niveau_scolaire_id", "option_scolaire_id", "etablissement_scolaire_id", "statut_verification_enseignant"):
        op.drop_index(f"ix_utilisateur_{col}", table_name="utilisateur")
    with op.batch_alter_table("utilisateur") as batch:
        for name in ("fk_utilisateur_verification_enseignant", "fk_utilisateur_etablissement_scolaire", "fk_utilisateur_option_scolaire", "fk_utilisateur_niveau_scolaire"):
            batch.drop_constraint(name, type_="foreignkey")
        for col in ("motif_refus_enseignant", "verification_enseignant_par_id", "verification_enseignant_le", "demande_enseignant_le", "statut_verification_enseignant", "etablissement_scolaire_id", "option_scolaire_id", "niveau_scolaire_id", "cycle_education", "profil_souhaite"):
            batch.drop_column(col)

    for table, indexes in {
        "etablissementscolaire": ["nom", "code", "type_etablissement", "secteur", "region", "district", "commune", "est_verifie", "est_actif"],
        "programmematierescolaire": ["referentiel_id", "niveau_id", "option_id", "matiere_id", "statut_validation"],
        "matierescolaire": ["code", "est_active", "statut_validation"],
        "optionscolaire": ["referentiel_id", "niveau_id", "est_active", "statut_validation", "type_option"],
        "niveauscolaire": ["referentiel_id", "code", "cycle", "est_actif", "statut_validation"],
        "referentielscolaire": ["code", "statut"],
    }.items():
        for col in indexes:
            op.drop_index(f"ix_{table}_{col}", table_name=table)
    for table in ("etablissementscolaire", "programmematierescolaire", "matierescolaire", "optionscolaire", "niveauscolaire", "referentielscolaire"):
        op.drop_table(table)
