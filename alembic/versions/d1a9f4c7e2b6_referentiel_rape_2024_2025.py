"""Separate the MEN RAPE 2024-2025 catalogue from legacy RAPS entries.

Revision ID: d1a9f4c7e2b6
Revises: c2f7a9e4b1d6

The RAPE edition is retained as historical data, not advertised as the
current 2026-2027 curriculum. Subjects are attached only to the exact grade
and series whose official MEN annual-program PDF was checked.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "d1a9f4c7e2b6"
down_revision = "c2f7a9e4b1d6"
branch_labels = None
depends_on = None

MEN_BASE = "https://www.education.gov.mg/wp-content/uploads/2024/09/"
MEN_INDEX = "https://www.education.gov.mg/repartition-annuelle-du-programme-detudes/"

NIVEAUX = (
    ("6E", "6e", "college", 1, "RAPE-T6_2024_2025.pdf"),
    ("5E", "5e", "college", 2, "RAPE-T7_2024_2025.pdf"),
    ("4E", "4e", "college", 3, "RAPE-T8_2024_2025.pdf"),
    ("3E", "3e", "college", 4, "RAPE-T9_2024_2025.pdf"),
    ("2NDE", "Seconde", "lycee", 5, "RAPE-T10_2024_2025.pdf"),
    ("1ERE", "Première", "lycee", 6, None),
    ("TERM", "Terminale", "lycee", 7, None),
)

SERIES = {
    ("1ERE", "L"): "RAPE-T11-L_2024_2025.pdf",
    ("1ERE", "S"): "RAPE-T11-S_2024_2025.pdf",
    ("1ERE", "OSE"): "RAPE-T11-OSE_2024_2025.pdf",
    ("TERM", "L"): "RAPE-T12-L_2024_2025.pdf",
    ("TERM", "S"): "RAPE-T12-S_2024_2025.pdf",
    ("TERM", "OSE"): "RAPE-T12-OSE_2024_2025.pdf",
}

MATIERES = {
    "MALAGASY": ("Malagasy", None),
    "FRANCAIS": ("Français", None),
    "ANGLAIS": ("Anglais", None),
    "EDUCATION_CITOYENNETE": ("Éducation à la citoyenneté", None),
    "HISTOIRE": ("Histoire", None),
    "GEOGRAPHIE": ("Géographie", None),
    "MATHEMATIQUES": ("Mathématiques", None),
    "PHYSIQUE_CHIMIE": ("Sciences physiques et chimiques", None),
    "SCIENCES_PHYSIQUES": ("Sciences physiques", None),
    "SCIENCES_ET_TECHNOLOGIE": ("Sciences et technologie", None),
    "SVT": ("Sciences de la vie et de la Terre", None),
    "MONDE_DU_TRAVAIL": ("Monde du travail", None),
    "ARTS": ("Arts", None),
    "EPS": ("Éducation physique et sportive", None),
    "SES": ("Sciences économiques et sociales", None),
    "PHILOSOPHIE": ("Philosophie", None),
    "TICE": ("Technologies de l'information et de la communication pour l'éducation", None),
}

PROGRAMMES = {
    ("6E", None): (
        "MALAGASY", "FRANCAIS", "ANGLAIS", "EDUCATION_CITOYENNETE",
        "MATHEMATIQUES", "SCIENCES_ET_TECHNOLOGIE", "GEOGRAPHIE",
        "HISTOIRE", "ARTS", "EPS",
    ),
    ("5E", None): (
        "MALAGASY", "FRANCAIS", "ANGLAIS", "EDUCATION_CITOYENNETE",
        "MATHEMATIQUES", "SCIENCES_PHYSIQUES", "SVT", "GEOGRAPHIE",
        "HISTOIRE", "MONDE_DU_TRAVAIL", "ARTS", "EPS",
    ),
    ("4E", None): (
        "MALAGASY", "FRANCAIS", "ANGLAIS", "EDUCATION_CITOYENNETE",
        "MATHEMATIQUES", "SCIENCES_PHYSIQUES", "SVT", "GEOGRAPHIE",
        "HISTOIRE", "MONDE_DU_TRAVAIL", "ARTS", "EPS",
    ),
    ("3E", None): (
        "MALAGASY", "FRANCAIS", "ANGLAIS", "EDUCATION_CITOYENNETE",
        "MATHEMATIQUES", "SCIENCES_PHYSIQUES", "SVT", "GEOGRAPHIE",
        "HISTOIRE", "MONDE_DU_TRAVAIL", "ARTS", "EPS",
    ),
    ("2NDE", None): (
        "MALAGASY", "FRANCAIS", "ANGLAIS", "HISTOIRE", "GEOGRAPHIE",
        "MATHEMATIQUES", "PHYSIQUE_CHIMIE", "SVT", "SES",
        "EDUCATION_CITOYENNETE", "EPS", "TICE",
    ),
    ("1ERE", "L"): (
        "MALAGASY", "FRANCAIS", "ANGLAIS", "HISTOIRE", "GEOGRAPHIE",
        "MATHEMATIQUES", "SCIENCES_PHYSIQUES", "SVT", "SES",
        "EDUCATION_CITOYENNETE", "PHILOSOPHIE", "EPS", "TICE",
    ),
    ("1ERE", "S"): (
        "MALAGASY", "FRANCAIS", "ANGLAIS", "HISTOIRE", "GEOGRAPHIE",
        "MATHEMATIQUES", "PHYSIQUE_CHIMIE", "SVT", "SES",
        "EDUCATION_CITOYENNETE", "PHILOSOPHIE", "EPS", "TICE",
    ),
    ("1ERE", "OSE"): (
        "MALAGASY", "FRANCAIS", "ANGLAIS", "HISTOIRE", "GEOGRAPHIE",
        "MATHEMATIQUES", "PHYSIQUE_CHIMIE", "SVT", "SES",
        "EDUCATION_CITOYENNETE", "PHILOSOPHIE", "EPS", "TICE",
    ),
    ("TERM", "L"): (
        "MALAGASY", "FRANCAIS", "ANGLAIS", "HISTOIRE", "GEOGRAPHIE",
        "MATHEMATIQUES", "PHYSIQUE_CHIMIE", "SVT", "SES", "PHILOSOPHIE", "EPS",
    ),
    ("TERM", "S"): (
        "MALAGASY", "FRANCAIS", "ANGLAIS", "HISTOIRE", "GEOGRAPHIE",
        "MATHEMATIQUES", "PHYSIQUE_CHIMIE", "SVT", "SES", "PHILOSOPHIE", "EPS",
    ),
    ("TERM", "OSE"): (
        "MALAGASY", "FRANCAIS", "ANGLAIS", "HISTOIRE", "GEOGRAPHIE",
        "MATHEMATIQUES", "PHYSIQUE_CHIMIE", "SVT", "SES", "PHILOSOPHIE", "EPS",
    ),
}


def _id(conn, table: str, where: str, params: dict) -> int:
    value = conn.execute(
        sa.text(f"SELECT id FROM {table} WHERE {where}"),
        params,
    ).scalar_one_or_none()
    if value is None:
        raise RuntimeError(f"Référentiel RAPE incomplet : {table} / {where}")
    return int(value)


def _ensure_referentiel(conn) -> int:
    code = "MEN-RAPE-2024-2025-historique"
    found = conn.execute(
        sa.text("SELECT id FROM referentielscolaire WHERE code=:code"),
        {"code": code},
    ).scalar_one_or_none()
    if found is not None:
        return int(found)
    conn.execute(
        sa.text(
            "INSERT INTO referentielscolaire "
            "(code, libelle, annee_scolaire, source_officielle, statut, date_creation) "
            "VALUES (:code, :libelle, '2024-2025', :source, 'historique', CURRENT_TIMESTAMP)"
        ),
        {
            "code": code,
            "libelle": "RAPE MEN — année scolaire 2024-2025 (référence historique)",
            "source": MEN_INDEX,
        },
    )
    return _id(conn, "referentielscolaire", "code=:code", {"code": code})


def _ensure_niveau(conn, ref_id: int, entry: tuple) -> int:
    code, libelle, cycle, ordre, pdf = entry
    source = MEN_BASE + pdf if pdf else MEN_INDEX
    conn.execute(
        sa.text(
            "INSERT INTO niveauscolaire "
            "(referentiel_id, code, libelle, cycle, ordre, est_actif, source_officielle, statut_validation) "
            "SELECT :ref, :code, :libelle, :cycle, :ordre, TRUE, :source, 'verifie' "
            "WHERE NOT EXISTS (SELECT 1 FROM niveauscolaire "
            "WHERE referentiel_id=:ref AND code=:code)"
        ),
        {"ref": ref_id, "code": code, "libelle": libelle, "cycle": cycle,
         "ordre": ordre, "source": source},
    )
    return _id(
        conn, "niveauscolaire", "referentiel_id=:ref AND code=:code",
        {"ref": ref_id, "code": code},
    )


def _ensure_option(conn, ref_id: int, niveau_id: int, code: str, pdf: str) -> int:
    libelle = "Série " + code
    source = MEN_BASE + pdf
    conn.execute(
        sa.text(
            "INSERT INTO optionscolaire "
            "(referentiel_id, niveau_id, code, libelle, type_option, est_active, source_officielle, statut_validation) "
            "SELECT :ref, :niveau, :code, :libelle, 'serie', TRUE, :source, 'verifie' "
            "WHERE NOT EXISTS (SELECT 1 FROM optionscolaire "
            "WHERE niveau_id=:niveau AND code=:code)"
        ),
        {"ref": ref_id, "niveau": niveau_id, "code": code,
         "libelle": libelle, "source": source},
    )
    return _id(
        conn, "optionscolaire", "niveau_id=:niveau AND code=:code",
        {"niveau": niveau_id, "code": code},
    )


def _ensure_matiere(conn, code: str, libelle: str) -> int:
    conn.execute(
        sa.text(
            "INSERT INTO matierescolaire "
            "(code, libelle, source_officielle, statut_validation, est_active) "
            "SELECT :code, :libelle, :source, 'verifie', TRUE "
            "WHERE NOT EXISTS (SELECT 1 FROM matierescolaire WHERE code=:code)"
        ),
        {"code": code, "libelle": libelle, "source": MEN_INDEX},
    )
    return _id(conn, "matierescolaire", "code=:code", {"code": code})


def _ensure_programme(
    conn, ref_id: int, niveau_id: int, option_id: int | None,
    matiere_id: int, source: str,
) -> None:
    if option_id is None:
        condition = "option_id IS NULL"
    else:
        condition = "option_id=:option"
    params = {
        "ref": ref_id,
        "niveau": niveau_id,
        "option": option_id,
        "matiere": matiere_id,
        "source": source,
    }
    conn.execute(
        sa.text(
            "INSERT INTO programmematierescolaire "
            "(referentiel_id, niveau_id, option_id, matiere_id, obligatoire, source_officielle, statut_validation) "
            "SELECT :ref, :niveau, :option, :matiere, TRUE, :source, 'verifie' "
            "WHERE NOT EXISTS (SELECT 1 FROM programmematierescolaire "
            "WHERE referentiel_id=:ref AND niveau_id=:niveau AND "
            + condition + " AND matiere_id=:matiere)"
        ),
        params,
    )


def upgrade() -> None:
    conn = op.get_bind()
    ref_id = _ensure_referentiel(conn)

    niveaux: dict[str, int] = {}
    for entry in NIVEAUX:
        niveaux[entry[0]] = _ensure_niveau(conn, ref_id, entry)

    options: dict[tuple[str, str], int] = {}
    for (code_niveau, code_serie), pdf in SERIES.items():
        options[(code_niveau, code_serie)] = _ensure_option(
            conn, ref_id, niveaux[code_niveau], code_serie, pdf
        )

    matiere_ids = {
        code: _ensure_matiere(conn, code, libelle)
        for code, (libelle, _malagasy) in MATIERES.items()
    }

    for (code_niveau, code_serie), codes_matieres in PROGRAMMES.items():
        niveau_id = niveaux[code_niveau]
        option_id = options[(code_niveau, code_serie)] if code_serie else None
        pdf = (
            SERIES[(code_niveau, code_serie)]
            if code_serie
            else next(item[4] for item in NIVEAUX if item[0] == code_niveau)
        )
        source = MEN_BASE + pdf
        for code_matiere in codes_matieres:
            _ensure_programme(
                conn, ref_id, niveau_id, option_id,
                matiere_ids[code_matiere], source,
            )


def downgrade() -> None:
    # Keep the historical catalogue and audit trail intact on rollback.
    # It can be hidden from default selectors without destructive deletion.
    pass
