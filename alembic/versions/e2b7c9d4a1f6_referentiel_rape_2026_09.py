"""Importe les programmes RAPE MEN, édition septembre 2026, comme version courante.

Revision ID: e2b7c9d4a1f6
Revises: d1a9f4c7e2b6

Les anciennes éditions RAPS/RAPE restent conservées en base sous leur propre
identifiant. Le RAPE 2026-09 est la version proposée par défaut. Il contient
les matières et leur répartition annuelle, pas l'intégralité des programmes
d'études : le référentiel reste donc marqué partiel.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "e2b7c9d4a1f6"
down_revision = "d1a9f4c7e2b6"
branch_labels = None
depends_on = None

MEN_INDEX = "https://plateforme.education.mg/bibliotheque-numerique/?lang=fr"
MEN_PDF_BASE = (
    "https://plateforme.education.mg/bibliotheque-numerique/"
    "theme/biblio/pix/pdf/"
)
CODE_REFERENTIEL = "MEN-RAPE-2026-09"

NIVEAUX = (
    ("6E", "6e", "college", 1, "RAPE_T6.pdf"),
    ("5E", "5e", "college", 2, "RAPE_T7.pdf"),
    ("4E", "4e", "college", 3, "RAPE_T8.pdf"),
    ("3E", "3e", "college", 4, "RAPE_T9.pdf"),
    ("2NDE", "Seconde", "lycee", 5, "RAPE_T10.pdf"),
    ("1ERE", "Première", "lycee", 6, None),
    ("TERM", "Terminale", "lycee", 7, None),
)

SERIES = {
    ("1ERE", "L"): "RAPE_T11_L.pdf",
    ("1ERE", "S"): "RAPE_T11_S.pdf",
    ("1ERE", "OSE"): "RAPE_T11_OSE.pdf",
    ("TERM", "L"): "RAPE_T12_L.pdf",
    ("TERM", "S"): "RAPE_T12_S.pdf",
    ("TERM", "OSE"): "RAPE_T12_OSE.pdf",
}

# Le code distingue FOV du cours « Éducation à la citoyenneté ».
# TIC en T10 et TICE en T11 sont également conservés comme libellés distincts.
MATIERES = {
    "MALAGASY": ("Malagasy", "Malagasy", "RAPE_T6.pdf"),
    "FRANCAIS": ("Français", "Frantsay", "RAPE_T6.pdf"),
    "ANGLAIS": ("Anglais", "Anglisy", "RAPE_T6.pdf"),
    "MATHEMATIQUES": ("Mathématiques", "Matematika", "RAPE_T6.pdf"),
    "SCIENCES_PHYSIQUES": ("Sciences physiques", "Siansa fizika", "RAPE_T6.pdf"),
    "SVT": ("Sciences de la vie et de la Terre", "Siansa momba ny aina sy ny tany", "RAPE_T6.pdf"),
    "HISTOIRE": ("Histoire", "Tantara", "RAPE_T6.pdf"),
    "GEOGRAPHIE": ("Géographie", "Jeografia", "RAPE_T6.pdf"),
    "FOV": (
        "Fanabeazana ho olom-pirenena vanona (FOV)",
        "Fanabeazana ho olom-pirenena vanona",
        "RAPE_T6.pdf",
    ),
    "ARTS": ("Arts", "Kanto", "RAPE_T6.pdf"),
    "EPS": (
        "Éducation physique et sportive",
        "Fanabeazana ara-batana sy ara-panatanjahantena",
        "RAPE_T6.pdf",
    ),
    "EDUCATION_CITOYENNETE": (
        "Éducation à la citoyenneté",
        "Fanabeazana olom-pirenena",
        "RAPE_T10.pdf",
    ),
    "SES": (
        "Sciences économiques et sociales",
        "Siansa ara-toekarena sy sosialy",
        "RAPE_T10.pdf",
    ),
    "TIC": (
        "Technologie de l'information et de la communication",
        "Teknolojian'ny fampahalalam-baovao sy fifandraisana",
        "RAPE_T10.pdf",
    ),
    "PHILOSOPHIE": ("Philosophie", "Filôzôfia", "RAPE_T11_L.pdf"),
    "TICE": (
        "Technologie de l'information et de la communication en éducation (TICE)",
        "Teknolojian'ny fampahalalam-baovao sy fifandraisana amin'ny fanabeazana",
        "RAPE_T11_L.pdf",
    ),
}

PROGRAMMES = {
    ("6E", None): (
        "MALAGASY", "FRANCAIS", "ANGLAIS", "MATHEMATIQUES",
        "SCIENCES_PHYSIQUES", "SVT", "HISTOIRE", "GEOGRAPHIE",
        "FOV", "ARTS", "EPS",
    ),
    ("5E", None): (
        "MALAGASY", "FRANCAIS", "ANGLAIS", "MATHEMATIQUES",
        "SCIENCES_PHYSIQUES", "SVT", "HISTOIRE", "GEOGRAPHIE",
        "FOV", "ARTS", "EPS",
    ),
    ("4E", None): (
        "MALAGASY", "FRANCAIS", "ANGLAIS", "MATHEMATIQUES",
        "SCIENCES_PHYSIQUES", "SVT", "HISTOIRE", "GEOGRAPHIE",
        "FOV", "ARTS", "EPS",
    ),
    ("3E", None): (
        "MALAGASY", "FRANCAIS", "ANGLAIS", "MATHEMATIQUES",
        "SCIENCES_PHYSIQUES", "SVT", "HISTOIRE", "GEOGRAPHIE",
        "FOV", "ARTS", "EPS",
    ),
    ("2NDE", None): (
        "MALAGASY", "FRANCAIS", "ANGLAIS", "MATHEMATIQUES",
        "SCIENCES_PHYSIQUES", "SVT", "HISTOIRE", "GEOGRAPHIE",
        "EDUCATION_CITOYENNETE", "SES", "EPS", "TIC",
    ),
    ("1ERE", "L"): (
        "MALAGASY", "FRANCAIS", "ANGLAIS", "MATHEMATIQUES",
        "SCIENCES_PHYSIQUES", "SVT", "HISTOIRE", "GEOGRAPHIE",
        "EDUCATION_CITOYENNETE", "SES", "EPS", "PHILOSOPHIE", "TICE",
    ),
    ("1ERE", "S"): (
        "MALAGASY", "FRANCAIS", "ANGLAIS", "MATHEMATIQUES",
        "SCIENCES_PHYSIQUES", "SVT", "HISTOIRE", "GEOGRAPHIE",
        "EDUCATION_CITOYENNETE", "SES", "EPS", "PHILOSOPHIE", "TICE",
    ),
    ("1ERE", "OSE"): (
        "MALAGASY", "FRANCAIS", "ANGLAIS", "MATHEMATIQUES",
        "SCIENCES_PHYSIQUES", "SVT", "HISTOIRE", "GEOGRAPHIE",
        "EDUCATION_CITOYENNETE", "SES", "EPS", "PHILOSOPHIE", "TICE",
    ),
    ("TERM", "L"): (
        "MALAGASY", "FRANCAIS", "ANGLAIS", "MATHEMATIQUES",
        "SCIENCES_PHYSIQUES", "SVT", "HISTOIRE", "GEOGRAPHIE",
        "SES", "EPS", "PHILOSOPHIE",
    ),
    ("TERM", "S"): (
        "MALAGASY", "FRANCAIS", "ANGLAIS", "MATHEMATIQUES",
        "SCIENCES_PHYSIQUES", "SVT", "HISTOIRE", "GEOGRAPHIE",
        "SES", "EPS", "PHILOSOPHIE",
    ),
    ("TERM", "OSE"): (
        "MALAGASY", "FRANCAIS", "ANGLAIS", "MATHEMATIQUES",
        "SCIENCES_PHYSIQUES", "SVT", "HISTOIRE", "GEOGRAPHIE",
        "SES", "EPS", "PHILOSOPHIE",
    ),
}


def _id(conn, table: str, where: str, params: dict) -> int:
    value = conn.execute(
        sa.text(f"SELECT id FROM {table} WHERE {where}"),
        params,
    ).scalar_one_or_none()
    if value is None:
        raise RuntimeError(f"RAPE septembre 2026 incomplet : {table} / {where}")
    return int(value)


def _ensure_referentiel(conn) -> int:
    existing = conn.execute(
        sa.text("SELECT id FROM referentielscolaire WHERE code=:code"),
        {"code": CODE_REFERENTIEL},
    ).scalar_one_or_none()
    if existing is not None:
        ref_id = int(existing)
        conn.execute(
            sa.text(
                "UPDATE referentielscolaire SET libelle=:libelle, "
                "annee_scolaire='2026-2027', source_officielle=:source, statut='partiel' "
                "WHERE id=:id"
            ),
            {
                "id": ref_id,
                "libelle": "RAPE MEN — édition septembre 2026 (référence courante)",
                "source": MEN_INDEX,
            },
        )
        return ref_id

    # Ces deux références ne sont plus proposées par défaut, mais leurs
    # associations et leurs IDs restent intacts pour les profils historiques.
    conn.execute(
        sa.text(
            "UPDATE referentielscolaire SET statut='historique' "
            "WHERE code IN ('MEN-RAPS-2024-2025-initial', "
            "'MEN-RAPE-2024-2025-historique')"
        )
    )
    conn.execute(
        sa.text(
            "INSERT INTO referentielscolaire "
            "(code, libelle, annee_scolaire, source_officielle, statut, date_creation) "
            "VALUES (:code, :libelle, '2026-2027', :source, 'partiel', CURRENT_TIMESTAMP)"
        ),
        {
            "code": CODE_REFERENTIEL,
            "libelle": "RAPE MEN — édition septembre 2026 (référence courante)",
            "source": MEN_INDEX,
        },
    )
    return _id(conn, "referentielscolaire", "code=:code", {"code": CODE_REFERENTIEL})


def _ensure_niveau(conn, ref_id: int, entry: tuple) -> int:
    code, libelle, cycle, ordre, pdf = entry
    source = MEN_PDF_BASE + pdf if pdf else MEN_INDEX
    conn.execute(
        sa.text(
            "INSERT INTO niveauscolaire "
            "(referentiel_id, code, libelle, cycle, ordre, est_actif, source_officielle, statut_validation) "
            "SELECT :ref, :code, :libelle, :cycle, :ordre, TRUE, :source, 'verifie' "
            "WHERE NOT EXISTS (SELECT 1 FROM niveauscolaire "
            "WHERE referentiel_id=:ref AND code=:code)"
        ),
        {
            "ref": ref_id, "code": code, "libelle": libelle,
            "cycle": cycle, "ordre": ordre, "source": source,
        },
    )
    return _id(
        conn, "niveauscolaire", "referentiel_id=:ref AND code=:code",
        {"ref": ref_id, "code": code},
    )


def _ensure_option(conn, ref_id: int, niveau_id: int, code: str, pdf: str) -> int:
    conn.execute(
        sa.text(
            "INSERT INTO optionscolaire "
            "(referentiel_id, niveau_id, code, libelle, type_option, est_active, source_officielle, statut_validation) "
            "SELECT :ref, :niveau, :code, :libelle, 'serie', TRUE, :source, 'verifie' "
            "WHERE NOT EXISTS (SELECT 1 FROM optionscolaire "
            "WHERE niveau_id=:niveau AND code=:code)"
        ),
        {
            "ref": ref_id,
            "niveau": niveau_id,
            "code": code,
            "libelle": "Série " + code,
            "source": MEN_PDF_BASE + pdf,
        },
    )
    return _id(
        conn, "optionscolaire", "niveau_id=:niveau AND code=:code",
        {"niveau": niveau_id, "code": code},
    )


def _ensure_matiere(conn, code: str, libelle: str, malagasy: str, source: str) -> int:
    existing = conn.execute(
        sa.text("SELECT id FROM matierescolaire WHERE code=:code"),
        {"code": code},
    ).scalar_one_or_none()
    if existing is not None:
        # Preserve a previously curated label in the user's language when
        # present, but refresh source/status to the official 2026 edition.
        conn.execute(
            sa.text(
                "UPDATE matierescolaire SET libelle=:libelle, "
                "libelle_malagasy=coalesce(nullif(libelle_malagasy, ''), :malagasy), "
                "source_officielle=:source, statut_validation='verifie', est_active=TRUE "
                "WHERE id=:id"
            ),
            {
                "id": int(existing),
                "libelle": libelle,
                "malagasy": malagasy,
                "source": source,
            },
        )
        return int(existing)

    conn.execute(
        sa.text(
            "INSERT INTO matierescolaire "
            "(code, libelle, libelle_malagasy, source_officielle, statut_validation, est_active) "
            "VALUES (:code, :libelle, :malagasy, :source, 'verifie', TRUE)"
        ),
        {
            "code": code, "libelle": libelle,
            "malagasy": malagasy, "source": source,
        },
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
    conn.execute(
        sa.text(
            "INSERT INTO programmematierescolaire "
            "(referentiel_id, niveau_id, option_id, matiere_id, obligatoire, source_officielle, statut_validation) "
            "SELECT :ref, :niveau, :option, :matiere, TRUE, :source, 'verifie' "
            "WHERE NOT EXISTS (SELECT 1 FROM programmematierescolaire "
            "WHERE referentiel_id=:ref AND niveau_id=:niveau AND "
            + condition + " AND matiere_id=:matiere)"
        ),
        {
            "ref": ref_id, "niveau": niveau_id,
            "option": option_id, "matiere": matiere_id, "source": source,
        },
    )


def upgrade() -> None:
    conn = op.get_bind()
    ref_id = _ensure_referentiel(conn)

    niveaux = {
        entry[0]: _ensure_niveau(conn, ref_id, entry)
        for entry in NIVEAUX
    }
    options = {
        (level, serie): _ensure_option(
            conn, ref_id, niveaux[level], serie, pdf
        )
        for (level, serie), pdf in SERIES.items()
    }
    matieres = {
        code: _ensure_matiere(
            conn, code, libelle, malagasy, MEN_INDEX
        )
        for code, (libelle, malagasy, _pdf) in MATIERES.items()
    }

    for (code_niveau, code_serie), codes_matieres in PROGRAMMES.items():
        niveau_id = niveaux[code_niveau]
        option_id = options[(code_niveau, code_serie)] if code_serie else None
        pdf = (
            SERIES[(code_niveau, code_serie)]
            if code_serie
            else next(entry[4] for entry in NIVEAUX if entry[0] == code_niveau)
        )
        source = MEN_PDF_BASE + pdf
        for code_matiere in codes_matieres:
            _ensure_programme(
                conn, ref_id, niveau_id, option_id,
                matieres[code_matiere], source,
            )


def downgrade() -> None:
    # Keep the verified annual curriculum and history intact on rollback.
    # The catalogue is hidden through its version status rather than deleted.
    pass
