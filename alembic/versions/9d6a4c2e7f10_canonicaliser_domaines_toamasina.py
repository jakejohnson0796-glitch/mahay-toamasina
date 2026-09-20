"""Canonicaliser les Domaines de l'Universite de Toamasina.

Revision ID: 9d6a4c2e7f10
Revises: 8c2e7a4d1f90

Le referentiel fourni distingue 6 domaines nationaux. Cette migration
corrige aussi les variantes d'accents/casse introduites par les anciennes
migrations et rattache les mentions Toamasina deja presentes, notamment
les 11 mentions ENS et les mentions des FST/FLSH.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import unicodedata

revision: str = "9d6a4c2e7f10"
down_revision: Union[str, None] = "8c2e7a4d1f90"
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


def _norm(texte: str | None) -> str:
    texte = (texte or "").strip().replace("\u2019", "'")
    texte = unicodedata.normalize("NFKD", texte)
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return " ".join(texte.lower().split())


def upgrade() -> None:
    conn = op.get_bind()

    toutes = conn.execute(sa.text("SELECT id, nom FROM domaine ORDER BY id")).fetchall()
    domaines = {}

    # Une cle normalisee correspond a un seul domaine national.
    for cible in DOMAINES:
        cible_norm = _norm(cible)
        candidats = [row for row in toutes if _norm(row[1]) == cible_norm]

        if not candidats:
            conn.execute(
                sa.text("INSERT INTO domaine (nom, est_active) VALUES (:nom, TRUE)")
                .bindparams(nom=cible)
            )
            identifiant = conn.execute(
                sa.text("SELECT id FROM domaine WHERE nom = :nom")
                .bindparams(nom=cible)
            ).scalar_one()
        else:
            identifiant = candidats[0][0]

            # Fusionne les doublons accent/casse s'ils proviennent des
            # anciennes migrations, sans jamais perdre un rattachement.
            for doublon_id, _doublon_nom in candidats[1:]:
                conn.execute(
                    sa.text(
                        "UPDATE mention SET domaine_id = :cible "
                        "WHERE domaine_id = :doublon"
                    ).bindparams(cible=identifiant, doublon=doublon_id)
                )
                conn.execute(
                    sa.text("DELETE FROM domaine WHERE id = :id")
                    .bindparams(id=doublon_id)
                )

            nom_actuel = conn.execute(
                sa.text("SELECT nom FROM domaine WHERE id = :id")
                .bindparams(id=identifiant)
            ).scalar_one()
            if nom_actuel != cible:
                conn.execute(
                    sa.text("UPDATE domaine SET nom = :nom WHERE id = :id")
                    .bindparams(nom=cible, id=identifiant)
                )

        domaines[cible_norm] = identifiant

    # Affectations explicites des mentions historiques/curatees.
    aliases = {
        "Droit et sciences politiques": {
            "droit et sciences politiques", "droit"
        },
        "Sciences économiques": {
            "sciences economiques", "economie"
        },
        "Sciences de gestion": {
            "gestion", "sciences de gestion"
        },
        "Sciences et technologie": {
            "mathematiques, informatique et applications",
            "mathematiques et informatique",
            "physique", "chimie", "physique-chimie",
            "sciences de la vie et de la terre",
        },
        "Sciences de l'éducation et didactique": {
            "sciences de l education et administration scolaire (seas)"
        },
        "Lettres et sciences humaines": {
            "etudes francaises", "etudes anglophones",
            "histoire-geographie", "philosophie",
            "histoire", "geographie", "anthropologie"
        },
    }

    mentions = conn.execute(sa.text("SELECT id, nom FROM mention")).fetchall()
    for domaine_nom, noms in aliases.items():
        did = domaines[_norm(domaine_nom)]
        for mid, nom in mentions:
            if _norm(nom) in {_norm(n) for n in noms}:
                conn.execute(
                    sa.text(
                        "UPDATE mention SET domaine_id = :did "
                        "WHERE id = :mid AND domaine_id IS NULL"
                    ).bindparams(did=did, mid=mid)
                )

    # Les mentions ENS sont reconnaissables par leur préfixe officiel dans
    # le référentiel Toamasina. Toutes restent dans le meme Domaine national.
    did_ens = domaines[_norm("Sciences de l'éducation et didactique")]
    for mid, nom in mentions:
        if _norm(nom).startswith("enseignement-apprentissage et didactique"):
            conn.execute(
                sa.text(
                    "UPDATE mention SET domaine_id = :did "
                    "WHERE id = :mid AND domaine_id IS NULL"
                ).bindparams(did=did_ens, mid=mid)
            )

    # Pour les trois composantes dont le Domaine est homogène dans le
    # fichier source, toute Mention deja utilisee par une Filiere de cette
    # composante recupere le domaine si elle etait encore NULL.
    for fragment_faculte, domaine_nom in (
        ("Sciences et Technologie", "Sciences et technologie"),
        ("École Normale Supérieure", "Sciences de l'éducation et didactique"),
        ("Lettres et Sciences Humaines", "Lettres et sciences humaines"),
    ):
        fac_rows = conn.execute(
            sa.text(
                "SELECT id FROM faculte WHERE lower(nom) LIKE lower(:nom)"
            ).bindparams(nom="%" + fragment_faculte + "%")
        ).fetchall()
        did = domaines[_norm(domaine_nom)]
        for (fid,) in fac_rows:
            conn.execute(
                sa.text(
                    """
                    UPDATE mention
                    SET domaine_id = :did
                    WHERE domaine_id IS NULL
                      AND id IN (
                          SELECT DISTINCT mention_id
                          FROM filiere
                          WHERE faculte_id = :fid
                            AND mention_id IS NOT NULL
                      )
                    """
                ).bindparams(did=did, fid=fid)
            )


def downgrade() -> None:
    pass
