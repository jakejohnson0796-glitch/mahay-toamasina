"""Ajoute le CFP Foulpointe et ses métiers issus de la cartographie officielle.

Revision ID: d2a7c5e9f840
Revises: c1e6b8a3d540

La cartographie METFP répertorie le CFP Foulpointe avec des métiers en menuiserie,
hôtellerie et restauration. Les offres sont importées sans année scolaire et
restent à vérifier : le répertoire ne prouve pas qu'une session ouvre en 2026-2027.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime

from alembic import op
import sqlalchemy as sa

revision = "d2a7c5e9f840"
down_revision = "c1e6b8a3d540"
branch_labels = None
depends_on = None

SOURCE_CARTOGRAPHIE = "https://www.metfp.gov.mg/cartographie"
NOM_ETABLISSEMENT = "CFP FOULPOINTE"
REGION = "ATSINANANA"
COMMUNE = "Foulpointe"

# Codes existants observés dans le catalogue déjà migré; le dernier métier est
# ajouté séparément parce que l'instantané initial ne le contenait pas.
PARCOURS = [
    {
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-MENUSIER-EN-BOIS",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Menusier en bois",
    },
    {
        "code": "TOURISME-HOTELLERIE-RESTAURATION-HOTELLERIE-FEMME-VALET-DE-CHAMBRE",
        "secteur": "Tourisme - Hôtellerie - Restauration",
        "filiere": "HOTELLERIE",
        "metier": "FEMME /VALET DE CHAMBRE",
    },
    {
        "code": "TOURISME-HOTELLERIE-RESTAURATION-HOTELLERIE-BARMAN",
        "secteur": "Tourisme - Hôtellerie - Restauration",
        "filiere": "HOTELLERIE",
        "metier": "BARMAN",
    },
    {
        "code": "TOURISME-HOTELLERIE-RESTAURATION-RESTAURATION-PATISSIER",
        "secteur": "Tourisme - Hôtellerie - Restauration",
        "filiere": "RESTAURATION",
        "metier": "PATISSIER",
    },
    {
        "code": "CUISINIER",
        "secteur": None,
        "filiere": None,
        "metier": "Cuisinier",
    },
    {
        "code": "TRAITEUR",
        "secteur": None,
        "filiere": None,
        "metier": "Traiteur",
    },
    {
        "code": "RESTAURATEUR-DE-MEUBLES",
        "secteur": None,
        "filiere": None,
        "metier": "Restaurateur de meubles",
    },
]


def _slug(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").upper()
    return value[:120] or "SANS-CODE"


def upgrade() -> None:
    conn = op.get_bind()
    maintenant = datetime.utcnow()

    # Le métier « Restaurateur de meubles » est explicitement listé par le METFP
    # avec secteur/filière non précisés dans la cartographie.
    for parcours in PARCOURS:
        existing = conn.execute(
            sa.text(
                "SELECT id FROM parcourstechniqueprofessionnel WHERE code=:code"
            ),
            {"code": parcours["code"]},
        ).first()
        if existing:
            continue
        conn.execute(
            sa.text(
                "INSERT INTO parcourstechniqueprofessionnel "
                "(code, secteur, filiere, metier, source_officielle, statut_validation, "
                "est_actif, date_creation, date_maj) "
                "VALUES (:code, :secteur, :filiere, :metier, :source, 'verifie', TRUE, :created, :updated)"
            ),
            {
                **parcours,
                "source": SOURCE_CARTOGRAPHIE,
                "created": maintenant,
                "updated": maintenant,
            },
        )

    row = conn.execute(
        sa.text(
            "SELECT id FROM etablissementscolaire WHERE lower(trim(nom))=lower(trim(:nom)) "
            "AND lower(trim(coalesce(region, '')))=lower(trim(:region))"
        ),
        {"nom": NOM_ETABLISSEMENT, "region": REGION},
    ).first()

    empreinte = hashlib.sha1(f"{REGION}|{NOM_ETABLISSEMENT}".encode("utf-8")).hexdigest()[:6].upper()
    code_etablissement = f"METFP-{_slug(REGION)[:10]}-{_slug(NOM_ETABLISSEMENT)[:14]}-{empreinte}"
    if row:
        etablissement_id = int(row[0])
        conn.execute(
            sa.text(
                "UPDATE etablissementscolaire SET "
                "code=coalesce(code, :code), type_etablissement='centre_formation', "
                "commune=coalesce(commune, :commune), source_officielle=:source, "
                "est_verifie=TRUE, est_actif=TRUE, date_maj=:updated WHERE id=:id"
            ),
            {
                "code": code_etablissement,
                "commune": COMMUNE,
                "source": SOURCE_CARTOGRAPHIE,
                "updated": maintenant,
                "id": etablissement_id,
            },
        )
    else:
        conn.execute(
            sa.text(
                "INSERT INTO etablissementscolaire "
                "(nom, code, type_etablissement, secteur, region, district, commune, "
                "source_officielle, est_verifie, est_actif, date_creation, date_maj) "
                "VALUES (:nom, :code, 'centre_formation', 'inconnu', :region, NULL, :commune, "
                ":source, TRUE, TRUE, :created, :updated)"
            ),
            {
                "nom": NOM_ETABLISSEMENT,
                "code": code_etablissement,
                "region": REGION,
                "commune": COMMUNE,
                "source": SOURCE_CARTOGRAPHIE,
                "created": maintenant,
                "updated": maintenant,
            },
        )
        etablissement_id = int(conn.execute(
            sa.text(
                "SELECT id FROM etablissementscolaire WHERE lower(trim(nom))=lower(trim(:nom)) "
                "AND lower(trim(coalesce(region, '')))=lower(trim(:region))"
            ),
            {"nom": NOM_ETABLISSEMENT, "region": REGION},
        ).scalar_one())

    # Toutes les offres de source sont en attente, non datées et donc non publiques.
    for parcours in PARCOURS:
        existing_path = conn.execute(
            sa.text(
                "SELECT id FROM parcourstechniqueprofessionnel WHERE code=:code"
            ),
            {"code": parcours["code"]},
        ).scalar_one()
        code_offre = "FORMATION:" + _slug(parcours["code"])
        existing_offer = conn.execute(
            sa.text(
                "SELECT id FROM offreetablissementscolaire "
                "WHERE etablissement_id=:etablissement AND code_offre=:code "
                "AND annee_scolaire IS NULL AND est_active=TRUE"
            ),
            {"etablissement": etablissement_id, "code": code_offre},
        ).first()
        if existing_offer:
            continue
        conn.execute(
            sa.text(
                "INSERT INTO offreetablissementscolaire "
                "(etablissement_id, code_offre, type_offre, niveau_scolaire_id, "
                "option_scolaire_id, matiere_scolaire_id, parcours_etfp_id, annee_scolaire, "
                "source_officielle, statut_validation, est_active, date_creation, date_maj) "
                "VALUES (:etablissement, :code, 'formation', NULL, NULL, NULL, :parcours, NULL, "
                ":source, 'a_verifier', TRUE, :created, :updated)"
            ),
            {
                "etablissement": etablissement_id,
                "code": code_offre,
                "parcours": existing_path,
                "source": SOURCE_CARTOGRAPHIE,
                "created": maintenant,
                "updated": maintenant,
            },
        )


def downgrade() -> None:
    # Ne pas détruire une offre qui aurait été complétée et validée manuellement.
    # Les données d'inventaire sont conservées pour préserver l'historique.
    pass
