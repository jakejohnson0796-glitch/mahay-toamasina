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
    code = "MEN-RAPS-2024-2025-initial"
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
                "libelle": "Référentiel scolaire initial — sources MEN disponibles 2024-2025",
                "annee": "2024-2025",
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
        "A": "Série A (programme antérieur)",
        "C": "Série C (programme antérieur)",
        "D": "Série D (programme antérieur)",
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

    # Le MEN indique que les anciennes séries A1/A2 convergent vers L,
    # et C/D vers S. Elles ne sont donc pas réintroduites comme options filles
    # de L/S sans source réglementaire qui justifie une telle hiérarchie.
    # parent_option_id reste disponible pour les options futures, à valider
    # explicitement par l'administration depuis une source officielle.

    # Les noms de matières ci-dessous sont repris des sommaires RAPS/RAPE du
    # MEN disponibles pour 2024-2025. Les associations non recoupées avec un
    # sommaire précis restent "a_verifier" et ne sont pas proposées aux élèves.
    matieres = [
        ("MALAGASY", "Malagasy", "Malagasy"),
        ("FRANCAIS", "Français", "Frantsay"),
        ("ANGLAIS", "Anglais", "Anglisy"),
        ("EDUCATION_CIVIQUE", "Éducation civique", "Fanabeazana olom-pirenena"),
        ("EDUCATION_CITOYENNETE", "Éducation à la citoyenneté", "Fanabeazana olom-pirenena"),
        ("HISTOIRE", "Histoire", "Tantara"),
        ("GEOGRAPHIE", "Géographie", "Jeografia"),
        ("MATHEMATIQUES", "Mathématiques", "Matematika"),
        ("PHYSIQUE_CHIMIE", "Sciences physiques et chimiques", "Fizika sy Simia"),
        ("SVT", "Sciences de la vie et de la Terre", "Siansa momba ny aina sy ny tany"),
        ("EPS", "Éducation physique et sportive", "Fanabeazana ara-batana sy ara-panatanjahantena"),
        ("PHILOSOPHIE", "Philosophie", "Filôzôfia"),
        ("SES", "Sciences économiques et sociales", "Siansa ara-toekarena sy sosialy"),
        ("TICE", "Technologie de l'information et de la communication en éducation (TICE)", "Teknolojian'ny fampahalalam-baovao sy fifandraisana"),
    ]
    for code_matiere, libelle, malagasy in matieres:
        conn.execute(
            sa.text(
                "INSERT INTO matierescolaire "
                "(code, libelle, libelle_malagasy, source_officielle, statut_validation, est_active) "
                "SELECT :code, :libelle, :malagasy, :source, 'verifie', TRUE "
                "WHERE NOT EXISTS (SELECT 1 FROM matierescolaire WHERE code=:code)"
            ),
            {
                "code": code_matiere,
                "libelle": libelle,
                "malagasy": malagasy,
                "source": SOURCE_PROGRAMMES,
            },
        )

    ids_matieres = {
        row[0]: row[1]
        for row in conn.execute(sa.text("SELECT code, id FROM matierescolaire")).all()
    }
    ids_niveaux = {
        row[0]: row[1]
        for row in conn.execute(
            sa.text("SELECT code, id FROM niveauscolaire WHERE referentiel_id=:ref"),
            {"ref": referentiel_id},
        ).all()
    }

    # Liens vers les documents officiels qui ont été retrouvés. Les séries
    # L/S/OSE sont présentes dans la filière de programmes RAPE, déployée
    # progressivement ; A/C/D restent recensées comme programmes historiques.
    base_men = "https://www.education.gov.mg/wp-content/uploads/2024/09/"
    sources_programmes = {
        "6E": base_men + "RAPS-6%C3%A8me_2024_2025.pdf",
        "5E": base_men + "RAPS-5%C3%A8me_2024_2025.pdf",
        "4E": base_men + "RAPS-4%C3%A8me_2024_2025.pdf",
        "3E": base_men + "RAPS-3%C3%A8me_2024_2025.pdf",
        "1ERE_A": base_men + "RAPS-1%C3%A8re-A_2024_2025.pdf",
        "1ERE_C": base_men + "RAPS-1%C3%A8re-C_2024_2025.pdf",
        "1ERE_D": base_men + "RAPS-1%C3%A8re-D_2024_2025.pdf",
        "TERM_A": base_men + "RAPS-Tle-A_2024_2025.pdf",
        "TERM_D": base_men + "RAPS-Tle-D_2024_2025.pdf",
        "1ERE_S": base_men + "RAPE-T11-S_2024_2025.pdf",
        "TERM_S": base_men + "RAPE-T12-S_2024_2025.pdf",
        "1ERE_OSE": base_men + "RAPE-T11-OSE_2024_2025.pdf",
        "TERM_OSE": base_men + "RAPE-T12-OSE_2024_2025.pdf",
    }

    def associer_matiere(
        code_niveau,
        code_matiere,
        source,
        code_serie=None,
        statut="a_verifier",
        obligatoire=True,
    ):
        niveau_id = ids_niveaux.get(code_niveau)
        matiere_id = ids_matieres.get(code_matiere)
        if not niveau_id or not matiere_id:
            return
        option_id = None
        if code_serie:
            option = conn.execute(
                sa.text(
                    "SELECT id FROM optionscolaire "
                    "WHERE referentiel_id=:ref AND niveau_id=:niveau "
                    "AND code=:code AND parent_option_id IS NULL"
                ),
                {"ref": referentiel_id, "niveau": niveau_id, "code": code_serie},
            ).first()
            if not option:
                return
            option_id = option[0]
            condition_option = "option_id=:option"
        else:
            condition_option = "option_id IS NULL"
        conn.execute(
            sa.text(
                "INSERT INTO programmematierescolaire "
                "(referentiel_id, niveau_id, option_id, matiere_id, obligatoire, source_officielle, statut_validation) "
                "SELECT :ref, :niveau, :option, :matiere, :obligatoire, :source, :statut "
                "WHERE NOT EXISTS (SELECT 1 FROM programmematierescolaire "
                "WHERE referentiel_id=:ref AND niveau_id=:niveau AND "
                + condition_option
                + " AND matiere_id=:matiere)"
            ),
            {
                "ref": referentiel_id,
                "niveau": niveau_id,
                "option": option_id,
                "matiere": matiere_id,
                "obligatoire": obligatoire,
                "source": source,
                "statut": statut,
            },
        )

    # Les sommaires RAPS de 6e, 4e et 3e énumèrent explicitement ces dix
    # disciplines. Pour la 5e, le PDF officiel est présent mais son sommaire
    # doit être recoupé avant publication de la liste.
    matieres_college = [
        "MALAGASY", "FRANCAIS", "ANGLAIS", "HISTOIRE", "GEOGRAPHIE",
        "MATHEMATIQUES", "PHYSIQUE_CHIMIE", "SVT", "EDUCATION_CIVIQUE", "EPS",
    ]
    for code_niveau in ("6E", "5E", "4E", "3E"):
        source = sources_programmes[code_niveau]
        statut = "a_verifier" if code_niveau == "5E" else "verifie"
        for code_matiere in matieres_college:
            associer_matiere(
                code_niveau, code_matiere, source,
                statut=statut,
            )

    # Les documents de Seconde A/C/D sont listés par le MEN, mais les matières
    # exactes ne sont pas attribuées automatiquement : ces lignes sont proposées
    # à l'admin en attente de validation depuis un sommaire par série.
    candidats_seconde = [
        "MALAGASY", "FRANCAIS", "ANGLAIS", "HISTOIRE", "GEOGRAPHIE",
        "MATHEMATIQUES", "PHYSIQUE_CHIMIE", "SVT", "EDUCATION_CIVIQUE", "EPS",
    ]
    for code_serie in ("A", "C", "D"):
        for code_matiere in candidats_seconde:
            associer_matiere(
                "2NDE", code_matiere, SOURCE_LYCEE,
                code_serie=code_serie, statut="a_verifier",
            )

    # Les associations sans série pour Première/Terminale sont des candidats,
    # pas une déclaration de tronc commun. L'admin peut les recouper avant
    # de les publier, ce qui évite d'attribuer une matière à la mauvaise série.
    candidats_lycee = [
        "MALAGASY", "FRANCAIS", "ANGLAIS", "HISTOIRE", "GEOGRAPHIE",
        "MATHEMATIQUES", "PHYSIQUE_CHIMIE", "SVT", "EPS",
        "PHILOSOPHIE", "SES", "EDUCATION_CITOYENNETE", "TICE",
    ]
    for code_niveau in ("1ERE", "TERM"):
        for code_matiere in candidats_lycee:
            associer_matiere(
                code_niveau, code_matiere,
                SOURCE_PROGRAMMES,
                statut="a_verifier",
            )

    # Programmes historiques avec sommaires disponibles : seuls les contenus
    # explicitement présents dans les documents cités sont publiés par défaut.
    programme_1ere_d = [
        "MALAGASY", "FRANCAIS", "ANGLAIS", "HISTOIRE", "GEOGRAPHIE",
        "MATHEMATIQUES", "PHYSIQUE_CHIMIE", "SVT", "EPS",
    ]
    programme_term_a = [
        "MALAGASY", "FRANCAIS", "ANGLAIS", "HISTOIRE", "MATHEMATIQUES",
        "PHYSIQUE_CHIMIE", "SVT", "EPS", "PHILOSOPHIE",
    ]
    programme_term_d = programme_1ere_d + ["PHILOSOPHIE"]
    for code_matiere in programme_1ere_d:
        associer_matiere(
            "1ERE", code_matiere, sources_programmes["1ERE_D"],
            code_serie="D", statut="verifie",
        )
    for code_matiere in programme_term_a:
        associer_matiere(
            "TERM", code_matiere, sources_programmes["TERM_A"],
            code_serie="A", statut="verifie",
        )
    for code_matiere in programme_term_d:
        associer_matiere(
            "TERM", code_matiere, sources_programmes["TERM_D"],
            code_serie="D", statut="verifie",
        )

    # Sommaires RAPE 2024-2025 de Première/Terminale S et OSE. Les matières
    # optionnelles nouvelles ne sont pas propagées aux séries A/C/D.
    programme_t11_s_ose = [
        "MALAGASY", "FRANCAIS", "ANGLAIS", "HISTOIRE", "GEOGRAPHIE",
        "MATHEMATIQUES", "PHYSIQUE_CHIMIE", "SVT", "SES",
        "EDUCATION_CITOYENNETE", "PHILOSOPHIE", "EPS", "TICE",
    ]
    programme_t12_s = [
        "MALAGASY", "FRANCAIS", "ANGLAIS", "HISTOIRE", "GEOGRAPHIE",
        "MATHEMATIQUES", "PHYSIQUE_CHIMIE", "SVT", "SES", "PHILOSOPHIE", "EPS",
    ]
    programme_t12_ose = [
        "MALAGASY", "FRANCAIS", "ANGLAIS", "HISTOIRE", "GEOGRAPHIE",
        "MATHEMATIQUES", "PHYSIQUE_CHIMIE", "SVT", "SES", "PHILOSOPHIE",
    ]
    for code_matiere in programme_t11_s_ose:
        associer_matiere(
            "1ERE", code_matiere, sources_programmes["1ERE_S"],
            code_serie="S", statut="verifie",
        )
        associer_matiere(
            "1ERE", code_matiere, sources_programmes["1ERE_OSE"],
            code_serie="OSE", statut="verifie",
        )
    for code_matiere in programme_t12_s:
        associer_matiere(
            "TERM", code_matiere, sources_programmes["TERM_S"],
            code_serie="S", statut="verifie",
        )
    for code_matiere in programme_t12_ose:
        associer_matiere(
            "TERM", code_matiere, sources_programmes["TERM_OSE"],
            code_serie="OSE", statut="verifie",
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
        sa.Column("parent_option_id", sa.Integer(), sa.ForeignKey("optionscolaire.id"), nullable=True),
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
    op.create_index("ix_optionscolaire_parent_option_id", "optionscolaire", ["parent_option_id"])
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
    # Huit index partiels uniques remplacent l'index à COALESCE (expression).
    # Ils couvrent chaque combinaison NULL/non-NULL des trois dimensions
    # facultatives, en restant réversibles par Alembic sur SQLite.
    dimensions_optionnelles = [
        "option_scolaire_id",
        "etablissement_scolaire_id",
        "matiere_scolaire_id",
    ]
    for masque in range(8):
        colonnes = ["niveau_scolaire_id"] + [
            colonne for bit, colonne in enumerate(dimensions_optionnelles)
            if masque & (1 << bit)
        ]
        conditions = [
            "statut = 'ACTIF'",
            "portee_academique = 'scolaire'",
            "niveau_scolaire_id IS NOT NULL",
        ]
        conditions.extend(
            f"{colonne} IS {'NOT ' if masque & (1 << bit) else ''}NULL"
            for bit, colonne in enumerate(dimensions_optionnelles)
        )
        condition = " AND ".join(conditions)
        op.create_index(
            f"ix_cercle_scolaire_unique_{masque:03b}",
            "cercleetude",
            colonnes,
            unique=True,
            postgresql_where=sa.text(condition),
            sqlite_where=sa.text(condition),
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

    # Les index doivent être supprimés AVANT le batch SQLite qui reconstruit
    # la table ; sinon Alembic tente de recréer un index sur une colonne retirée.
    for col in ("niveau_scolaire_id", "option_scolaire_id"):
        op.drop_index(f"ix_tentativequiz_{col}", table_name="tentativequiz")
    with op.batch_alter_table("tentativequiz") as batch:
        batch.drop_constraint("fk_tentativequiz_option_scolaire", type_="foreignkey")
        batch.drop_constraint("fk_tentativequiz_niveau_scolaire", type_="foreignkey")
        batch.drop_column("option_scolaire_id")
        batch.drop_column("niveau_scolaire_id")
        batch.drop_column("cycle_education")

    for masque in range(8):
        op.drop_index(f"ix_cercle_scolaire_unique_{masque:03b}", table_name="cercleetude")
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
        "optionscolaire": ["referentiel_id", "niveau_id", "parent_option_id", "est_active", "statut_validation", "type_option"],
        "niveauscolaire": ["referentiel_id", "code", "cycle", "est_actif", "statut_validation"],
        "referentielscolaire": ["code", "statut"],
    }.items():
        for col in indexes:
            op.drop_index(f"ix_{table}_{col}", table_name=table)
    for table in ("etablissementscolaire", "programmematierescolaire", "matierescolaire", "optionscolaire", "niveauscolaire", "referentielscolaire"):
        op.drop_table(table)
