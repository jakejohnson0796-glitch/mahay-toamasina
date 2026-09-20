"""Rattacher les mentions de Toamasina aux Domaines du referentiel source.

Revision ID: 8c2e7a4d1f90
Revises: f4b7c9d1e2a6

Le classeur academique de l'Universite de Toamasina fourni avec le projet
definit 6 domaines. La migration est volontairement conservative :
- elle cree ces domaines s'ils n'existent pas ;
- elle rattache uniquement des Mentions deja presentes en base ;
- elle ne cree ni ne supprime de Mention/Filiere ;
- elle ne remplace pas un domaine deja renseigne par un admin.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8c2e7a4d1f90"
down_revision: Union[str, None] = "f4b7c9d1e2a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DOMAINES = (
    "Droit et sciences politiques",
    "Sciences économiques",
    "Sciences de gestion",
    "Sciences et technologie",
    "Sciences de l'éducation et didactique",
    "Lettres et sciences humaines",
)

MENTIONS_PAR_DOMAINE = {
    "Droit et sciences politiques": (
        "Droit et Sciences politiques",
        "Droit et Sciences Politiques",
        "Droit",
    ),
    "Sciences économiques": (
        "Sciences Économiques",
        "Sciences Economiques",
        "Economie",
    ),
    "Sciences de gestion": (
        "Gestion",
        "Sciences de Gestion",
    ),
    "Sciences et technologie": (
        "Mathématiques, Informatique et Applications",
        "Mathematiques, Informatique et Applications",
        "Mathematiques et Informatique",
        "Physique",
        "Chimie",
        "Physique-Chimie",
        "Sciences de la Vie et de la Terre",
        "Sciences de la Vie et de la Terre",
    ),
    "Sciences de l'éducation et didactique": (
        "Sciences de l'Education et Administration Scolaire (SEAS)",
    ),
    "Lettres et sciences humaines": (
        "Études Françaises",
        "Etudes Francaises",
        "Études Anglophones",
        "Etudes Anglophones",
        "Histoire",
        "Géographie",
        "Histoire-Geographie",
        "Philosophie",
        "Anthropologie",
    ),
}


def _normaliser(valeur: str) -> str:
    import unicodedata
    texte = (valeur or "").strip().replace("\u2019", "'")
    texte = unicodedata.normalize("NFKD", texte)
    return "".join(c for c in texte if not unicodedata.combining(c)).lower()


def upgrade() -> None:
    conn = op.get_bind()

    domaines = {}
    for nom in DOMAINES:
        row = conn.execute(
            sa.text("SELECT id FROM domaine WHERE lower(nom) = lower(:nom)")
            .bindparams(nom=nom)
        ).first()
        if row:
            domaines[_normaliser(nom)] = row[0]
            continue
        conn.execute(
            sa.text("INSERT INTO domaine (nom, est_active) VALUES (:nom, TRUE)")
            .bindparams(nom=nom)
        )
        new_id = conn.execute(
            sa.text("SELECT id FROM domaine WHERE lower(nom) = lower(:nom)")
            .bindparams(nom=nom)
        ).scalar()
        domaines[_normaliser(nom)] = new_id

    for domaine_nom, noms_mentions in MENTIONS_PAR_DOMAINE.items():
        domaine_id = domaines[_normaliser(domaine_nom)]
        for mention_nom in noms_mentions:
            conn.execute(
                sa.text(
                    "UPDATE mention "
                    "SET domaine_id = :did "
                    "WHERE domaine_id IS NULL AND lower(nom) = lower(:nom)"
                ).bindparams(did=domaine_id, nom=mention_nom)
            )


def downgrade() -> None:
    # Pas de rollback destructif : des rattachements peuvent avoir ete
    # corriges manuellement apres cette migration.
    pass
