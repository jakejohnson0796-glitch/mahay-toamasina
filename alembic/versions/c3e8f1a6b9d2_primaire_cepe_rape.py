"""Ajoute le primaire T1-T5 et le parcours CEPE au RAPE MEN 2026."""

from alembic import op
import sqlalchemy as sa


revision = "c3e8f1a6b9d2"
down_revision = "b7e2c9a4d1f6"
branch_labels = None
depends_on = None

MEN_INDEX = "https://plateforme.education.mg/bibliotheque-numerique/?lang=fr"
MEN_PDF_BASE = "https://plateforme.education.mg/bibliotheque-numerique/theme/biblio/pix/pdf/"
CODE_REFERENTIEL = "MEN-RAPE-2026-09"

NIVEAUX = (
    ("T1", "T1", 1, "RAPE_T1.pdf"),
    ("T2", "T2", 2, "RAPE_T2.pdf"),
    ("T3", "T3", 3, "RAPE_T3.pdf"),
    ("T4", "T4", 4, "RAPE_T4.pdf"),
    ("T5", "T5", 5, "RAPE_T5.pdf"),
)

MATIERES = {
    "KAJY": ("Kajy", "Kajy"),
    "CONNAISSANCES_USUELLES": ("Connaissances usuelles", "Fahalalana ankapobeny"),
}

PROGRAMMES = {
    "T1": ("KAJY", "MALAGASY", "FRANCAIS", "FOV", "MATHEMATIQUES", "EPS", "ARTS"),
    "T2": ("KAJY", "MALAGASY", "FRANCAIS"),
    "T3": ("KAJY", "CONNAISSANCES_USUELLES", "HISTOIRE", "GEOGRAPHIE", "MALAGASY", "FRANCAIS"),
    "T4": ("KAJY", "CONNAISSANCES_USUELLES", "HISTOIRE", "GEOGRAPHIE", "MALAGASY", "FRANCAIS"),
    "T5": ("KAJY", "CONNAISSANCES_USUELLES", "HISTOIRE", "GEOGRAPHIE", "MALAGASY", "FRANCAIS"),
}


def _id(conn, table: str, where: str, params: dict) -> int:
    value = conn.execute(sa.text(f"SELECT id FROM {table} WHERE {where}"), params).scalar_one_or_none()
    if value is None:
        raise RuntimeError(f"RAPE primaire incomplet : {table} / {where}")
    return int(value)


def _ensure_matiere(conn, code: str, libelle: str, malagasy: str, source: str) -> int:
    existing = conn.execute(sa.text("SELECT id FROM matierescolaire WHERE code=:code"), {"code": code}).scalar_one_or_none()
    if existing is not None:
        conn.execute(
            sa.text(
                "UPDATE matierescolaire SET libelle=:libelle, "
                "libelle_malagasy=coalesce(nullif(libelle_malagasy, ''), :malagasy), "
                "source_officielle=:source, statut_validation='verifie', est_active=TRUE WHERE id=:id"
            ),
            {"id": int(existing), "libelle": libelle, "malagasy": malagasy, "source": source},
        )
        return int(existing)
    conn.execute(
        sa.text(
            "INSERT INTO matierescolaire "
            "(code, libelle, libelle_malagasy, source_officielle, statut_validation, est_active) "
            "VALUES (:code, :libelle, :malagasy, :source, 'verifie', TRUE)"
        ),
        {"code": code, "libelle": libelle, "malagasy": malagasy, "source": source},
    )
    return _id(conn, "matierescolaire", "code=:code", {"code": code})


def _ensure_niveau(conn, ref_id: int, code: str, libelle: str, ordre: int, pdf: str) -> int:
    source = MEN_PDF_BASE + pdf
    conn.execute(
        sa.text(
            "INSERT INTO niveauscolaire "
            "(referentiel_id, code, libelle, cycle, ordre, est_actif, source_officielle, statut_validation) "
            "SELECT :ref, :code, :libelle, 'primaire', :ordre, TRUE, :source, 'verifie' "
            "WHERE NOT EXISTS (SELECT 1 FROM niveauscolaire WHERE referentiel_id=:ref AND code=:code)"
        ),
        {"ref": ref_id, "code": code, "libelle": libelle, "ordre": ordre, "source": source},
    )
    return _id(conn, "niveauscolaire", "referentiel_id=:ref AND code=:code", {"ref": ref_id, "code": code})


def _ensure_programme(conn, ref_id: int, niveau_id: int, matiere_id: int, source: str) -> None:
    conn.execute(
        sa.text(
            "INSERT INTO programmematierescolaire "
            "(referentiel_id, niveau_id, option_id, matiere_id, obligatoire, source_officielle, statut_validation) "
            "SELECT :ref, :niveau, NULL, :matiere, TRUE, :source, 'verifie' "
            "WHERE NOT EXISTS (SELECT 1 FROM programmematierescolaire "
            "WHERE referentiel_id=:ref AND niveau_id=:niveau AND option_id IS NULL AND matiere_id=:matiere)"
        ),
        {"ref": ref_id, "niveau": niveau_id, "matiere": matiere_id, "source": source},
    )


def upgrade() -> None:
    conn = op.get_bind()
    ref_id = _id(conn, "referentielscolaire", "code=:code", {"code": CODE_REFERENTIEL})
    matieres = {
        code: _ensure_matiere(conn, code, libelle, malagasy, MEN_INDEX)
        for code, (libelle, malagasy) in MATIERES.items()
    }
    for code in ("MALAGASY", "FRANCAIS", "MATHEMATIQUES", "FOV", "EPS", "ARTS", "HISTOIRE", "GEOGRAPHIE"):
        matieres[code] = _id(conn, "matierescolaire", "code=:code", {"code": code})
    for code, libelle, ordre, pdf in NIVEAUX:
        level_id = _ensure_niveau(conn, ref_id, code, libelle, ordre, pdf)
        source = MEN_PDF_BASE + pdf
        for subject in PROGRAMMES[code]:
            _ensure_programme(conn, ref_id, level_id, matieres[subject], source)

    with op.batch_alter_table("cycleenseigne", recreate="always") as batch:
        batch.drop_constraint("ck_cycleenseigne_cycle", type_="check")
        batch.create_check_constraint(
            "ck_cycleenseigne_cycle",
            "cycle_education IN ('primaire', 'college', 'lycee', 'universite')",
        )


def downgrade() -> None:
    # Les profils, documents et déclarations peuvent déjà référencer ces niveaux.
    # Les données sont donc conservées pour éviter une suppression destructive.
    pass
