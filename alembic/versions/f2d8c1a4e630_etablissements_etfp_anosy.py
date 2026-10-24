"""Ajoute les établissements ETFP répertoriés par la cartographie METFP en Anosy.

Revision ID: f2d8c1a4e630
Revises: e3b9c6a1d740

Les offres importées restent non datées et à vérifier : le catalogue de centres
ne signifie pas que leurs métiers sont ouverts au recrutement cette année.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime

from alembic import op
import sqlalchemy as sa

revision = "f2d8c1a4e630"
down_revision = "e3b9c6a1d740"
branch_labels = None
depends_on = None

SOURCE_CARTOGRAPHIE = "https://www.metfp.gov.mg/cartographie"

PARCOURS_A_AJOUTER = [
    {
        "code": "GESTION-GESTION-COMPTABLE-AGENT-COMPTABLE",
        "secteur": "Gestion",
        "filiere": "GESTION COMPTABLE",
        "metier": "AGENT COMPTABLE",
    },
    {
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-CHEF-D-EQUIPE-DE-CHANTIER",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Chef d'Equipe de chantier",
    },
    {
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-DISSANATEUR-PROJETEUR-METREUR",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Dissanateur Projeteur Métreur",
    },
    {
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-CARRELEUR",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Carreleur",
    },
    {
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-ARCHITECTE",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Architecte",
    },
    {
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-DECORATEUR-D-INTERIEUR",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Décorateur d'intérieur",
    },
    {
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-TOPOGRAPHE",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Topographe",
    },
    {
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-COMMIS-DE-CHANTIER",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Commis de chantier",
    },
    {
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-MENUSIER-EN-BOIS",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Menusier en bois",
    },
    {
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-ELECTRICIEN-BATIMENT",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Electricien bâtiment",
    },
    {
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-POSEUR-DE-PAVE",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Poseur de pavé",
    },
    {
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-MENUISIER-ALUMINIUM",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Menuisier aluminium",
    },
    {
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-AIDE-PLOMBIER",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Aide plombier",
    },
    {
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-PLATRIER",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Plâtrier",
    },
    {
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-CONDUCTEUR-DE-GRUE",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Conducteur de grue",
    },
    {
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-CONDUCTEUR-D-ENGIN",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Conducteur d'engin",
    },
    {
        "code": "DEVELOPPEMENT-RURAL-ELEVAGE-AGENTS-D-ELEVAGE",
        "secteur": "Developpement Rural",
        "filiere": "ELEVAGE",
        "metier": "AGENTS D'ELEVAGE",
    },
    {
        "code": "DEVELOPPEMENT-RURAL-ELEVAGE-TECHNICIEN-D-ELEVAGE",
        "secteur": "Developpement Rural",
        "filiere": "ELEVAGE",
        "metier": "TECHNICIEN D'ELEVAGE",
    },
    {
        "code": "DEVELOPPEMENT-RURAL-ELEVAGE-ELEVEUR-DE-PORC",
        "secteur": "Developpement Rural",
        "filiere": "ELEVAGE",
        "metier": "ELEVEUR DE PORC",
    },
    {
        "code": "DEVELOPPEMENT-RURAL-ELEVAGE-AVICULTEUR",
        "secteur": "Developpement Rural",
        "filiere": "ELEVAGE",
        "metier": "AVICULTEUR",
    },
    {
        "code": "DEVELOPPEMENT-RURAL-ELEVAGE-APICULTEUR",
        "secteur": "Developpement Rural",
        "filiere": "ELEVAGE",
        "metier": "APICULTEUR",
    },
    {
        "code": "TEXTILE-HABILLEMENT-ACCESSOIRES-COUPE-ET-COUTURE-COUTURIER-E",
        "secteur": "Textile - Habillement - Accessoires",
        "filiere": "COUPE ET COUTURE",
        "metier": "COUTURIER (E)",
    },
    {
        "code": "TEXTILE-HABILLEMENT-ACCESSOIRES-COUPE-ET-COUTURE-TAILLEUR-COUTURIER",
        "secteur": "Textile - Habillement - Accessoires",
        "filiere": "COUPE ET COUTURE",
        "metier": "TAILLEUR COUTURIER",
    },
    {
        "code": "TEXTILE-HABILLEMENT-ACCESSOIRES-VANNERIE-VANNIER",
        "secteur": "Textile - Habillement - Accessoires",
        "filiere": "VANNERIE",
        "metier": "VANNIER",
    },
    {
        "code": "TEXTILE-HABILLEMENT-ACCESSOIRES-VANNERIE-TISSERAND",
        "secteur": "Textile - Habillement - Accessoires",
        "filiere": "VANNERIE",
        "metier": "TISSERAND",
    },
    {
        "code": "DEVELOPPEMENT-RURAL-AGRICULTURE-AGENT-D-AGRICULTURE",
        "secteur": "Developpement Rural",
        "filiere": "AGRICULTURE",
        "metier": "AGENT D'AGRICULTURE",
    },
    {
        "code": "OUVRIER-DE-FERME-D-ELEVAGE",
        "secteur": None,
        "filiere": None,
        "metier": "Ouvrier de ferme d’élevage",
    },
]

ETABLISSEMENTS = [
    {
        "nom": "LTP BETROKA",
        "region": "ANOSY",
        "type": "lycee_technique",
        "commune": "Betroka",
        "keys": ["GESTION-GESTION-COMPTABLE-AGENT-COMPTABLE","GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-CHEF-D-EQUIPE-DE-CHANTIER","GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-DISSANATEUR-PROJETEUR-METREUR","GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-CARRELEUR","GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-ARCHITECTE","GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-DECORATEUR-D-INTERIEUR","GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-TOPOGRAPHE","GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-COMMIS-DE-CHANTIER","GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-MENUSIER-EN-BOIS","GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-ELECTRICIEN-BATIMENT","GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-POSEUR-DE-PAVE","GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-MENUISIER-ALUMINIUM","GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-AIDE-PLOMBIER","GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-PLATRIER","GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-CONDUCTEUR-DE-GRUE","GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-CONDUCTEUR-D-ENGIN"],
    },
    {
        "nom": "CFPF ISOANALA",
        "region": "ANOSY",
        "type": "centre_formation_specialise",
        "commune": "Isoanala",
        "keys": ["DEVELOPPEMENT-RURAL-ELEVAGE-AGENTS-D-ELEVAGE","DEVELOPPEMENT-RURAL-ELEVAGE-TECHNICIEN-D-ELEVAGE","DEVELOPPEMENT-RURAL-ELEVAGE-ELEVEUR-DE-PORC","DEVELOPPEMENT-RURAL-ELEVAGE-AVICULTEUR","DEVELOPPEMENT-RURAL-ELEVAGE-APICULTEUR","TEXTILE-HABILLEMENT-ACCESSOIRES-COUPE-ET-COUTURE-COUTURIER-E","TEXTILE-HABILLEMENT-ACCESSOIRES-COUPE-ET-COUTURE-TAILLEUR-COUTURIER","TEXTILE-HABILLEMENT-ACCESSOIRES-VANNERIE-VANNIER","TEXTILE-HABILLEMENT-ACCESSOIRES-VANNERIE-TISSERAND"],
    },
    {
        "nom": "LTA AMPASY NAHAMPOANA",
        "region": "ANOSY",
        "type": "lycee_technique",
        "commune": "Ampasy Nahampoana",
        "keys": ["DEVELOPPEMENT-RURAL-AGRICULTURE-AGENT-D-AGRICULTURE","OUVRIER-DE-FERME-D-ELEVAGE","GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-PLATRIER","GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-CONDUCTEUR-DE-GRUE","GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-CONDUCTEUR-D-ENGIN"],
    },
]


def _slug(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").upper()
    return value[:120] or "SANS-CODE"


def _assurer_parcours(conn, maintenant: datetime) -> None:
    for parcours in PARCOURS_A_AJOUTER:
        existe = conn.execute(
            sa.text("SELECT id FROM parcourstechniqueprofessionnel WHERE code=:code"),
            {"code": parcours["code"]},
        ).first()
        if existe:
            continue
        conn.execute(
            sa.text(
                "INSERT INTO parcourstechniqueprofessionnel "
                "(code, secteur, filiere, metier, source_officielle, statut_validation, "
                "est_actif, date_creation, date_maj) "
                "VALUES (:code, :secteur, :filiere, :metier, :source, 'verifie', TRUE, :created, :updated)"
            ),
            {**parcours, "source": SOURCE_CARTOGRAPHIE, "created": maintenant, "updated": maintenant},
        )


def _chemin_id(conn, code: str) -> int:
    identifiant = conn.execute(
        sa.text("SELECT id FROM parcourstechniqueprofessionnel WHERE code=:code"),
        {"code": code},
    ).scalar()
    if identifiant is None:
        raise RuntimeError(f"Le parcours ETFP requis manque au référentiel : {code}")
    return int(identifiant)


def _assurer_offre(conn, site_id: int, code_parcours: str, maintenant: datetime) -> None:
    parcours_id = _chemin_id(conn, code_parcours)
    code_offre = "FORMATION:" + _slug(code_parcours)
    existe = conn.execute(
        sa.text(
            "SELECT id FROM offreetablissementscolaire WHERE etablissement_id=:site "
            "AND code_offre=:code AND annee_scolaire IS NULL AND est_active=TRUE"
        ),
        {"site": site_id, "code": code_offre},
    ).first()
    if existe:
        return
    conn.execute(
        sa.text(
            "INSERT INTO offreetablissementscolaire "
            "(etablissement_id, code_offre, type_offre, niveau_scolaire_id, option_scolaire_id, "
            "matiere_scolaire_id, parcours_etfp_id, annee_scolaire, source_officielle, "
            "statut_validation, est_active, date_creation, date_maj) "
            "VALUES (:site, :code, 'formation', NULL, NULL, NULL, :pathway, NULL, "
            ":source, 'a_verifier', TRUE, :created, :updated)"
        ),
        {
            "site": site_id, "code": code_offre, "pathway": parcours_id, "source": SOURCE_CARTOGRAPHIE,
            "created": maintenant, "updated": maintenant,
        },
    )


def upgrade() -> None:
    conn = op.get_bind()
    maintenant = datetime.utcnow()
    _assurer_parcours(conn, maintenant)
    for site in ETABLISSEMENTS:
        nom, region = site["nom"], site["region"]
        existant = conn.execute(
            sa.text(
                "SELECT id FROM etablissementscolaire WHERE lower(trim(nom))=lower(trim(:nom)) "
                "AND lower(trim(coalesce(region, '')))=lower(trim(:region))"
            ),
            {"nom": nom, "region": region},
        ).first()
        empreinte = hashlib.sha1(f"{region}|{nom}".encode("utf-8")).hexdigest()[:6].upper()
        code = f"METFP-{_slug(region)[:10]}-{_slug(nom)[:14]}-{empreinte}"
        params = {
            "code": code, "nom": nom, "region": region, "type": site["type"], "commune": site["commune"],
            "source": SOURCE_CARTOGRAPHIE, "created": maintenant, "updated": maintenant,
        }
        if existant:
            site_id = int(existant[0])
            conn.execute(
                sa.text(
                    "UPDATE etablissementscolaire SET code=coalesce(code, :code), "
                    "type_etablissement=:type, commune=coalesce(commune, :commune), "
                    "source_officielle=:source, est_verifie=TRUE, est_actif=TRUE, date_maj=:updated WHERE id=:id"
                ),
                {**params, "id": site_id},
            )
        else:
            conn.execute(
                sa.text(
                    "INSERT INTO etablissementscolaire "
                    "(nom, code, type_etablissement, secteur, region, district, commune, source_officielle, "
                    "est_verifie, est_actif, date_creation, date_maj) "
                    "VALUES (:nom, :code, :type, 'inconnu', :region, NULL, :commune, :source, "
                    "TRUE, TRUE, :created, :updated)"
                ),
                params,
            )
            site_id = int(conn.execute(
                sa.text(
                    "SELECT id FROM etablissementscolaire WHERE lower(trim(nom))=lower(trim(:nom)) "
                    "AND lower(trim(coalesce(region, '')))=lower(trim(:region))"
                ),
                {"nom": nom, "region": region},
            ).scalar_one())

        for code_parcours in sorted(set(site["keys"])):
            _assurer_offre(conn, site_id, code_parcours, maintenant)


def downgrade() -> None:
    # Ne pas retirer les données de répertoire ou les offres qui peuvent avoir été revues manuellement.
    pass
