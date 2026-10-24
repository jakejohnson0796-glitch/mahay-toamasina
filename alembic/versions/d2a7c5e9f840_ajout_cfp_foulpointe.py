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
        "metier": "Menusier en bois"
    },
    {
        "code": "TOURISME-HOTELLERIE-RESTAURATION-HOTELLERIE-FEMME-VALET-DE-CHAMBRE",
        "secteur": "Tourisme - Hôtellerie - Restauration",
        "filiere": "HOTELLERIE",
        "metier": "FEMME /VALET DE CHAMBRE"
    },
    {
        "code": "TOURISME-HOTELLERIE-RESTAURATION-HOTELLERIE-BARMAN",
        "secteur": "Tourisme - Hôtellerie - Restauration",
        "filiere": "HOTELLERIE",
        "metier": "BARMAN"
    },
    {
        "code": "TOURISME-HOTELLERIE-RESTAURATION-RESTAURATION-PATISSIER",
        "secteur": "Tourisme - Hôtellerie - Restauration",
        "filiere": "RESTAURATION",
        "metier": "PATISSIER"
    },
    {
        "code": "CUISINIER",
        "secteur": None,
        "filiere": None,
        "metier": "Cuisinier"
    },
    {
        "code": "TRAITEUR",
        "secteur": None,
        "filiere": None,
        "metier": "Traiteur"
    },
    {
        "code": "GESTION-GESTION-COMPTABLE-AGENT-COMPTABLE",
        "secteur": "Gestion",
        "filiere": "GESTION COMPTABLE",
        "metier": "AGENT COMPTABLE"
    },
    {
        "code": "INDUSTRIEL-FABRICATION-MECANIQUE-FRAISEUR",
        "secteur": "Industriel",
        "filiere": "FABRICATION MECANIQUE",
        "metier": "Fraiseur"
    },
    {
        "code": "INDUSTRIEL-ELECTRONIQUE-ELECTRONICIEN",
        "secteur": "Industriel",
        "filiere": "ELECTRONIQUE",
        "metier": "Electronicien"
    },
    {
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-CHEF-D-EQUIPE-DE-CHANTIER",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Chef d'Equipe de chantier"
    },
    {
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-DISSANATEUR-PROJETEUR-METREUR",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Dissanateur Projeteur Métreur"
    },
    {
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-CARRELEUR",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Carreleur"
    },
    {
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-ARCHITECTE",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Architecte"
    },
    {
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-DECORATEUR-D-INTERIEUR",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Décorateur d'intérieur"
    },
    {
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-TOPOGRAPHE",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Topographe"
    },
    {
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-COMMIS-DE-CHANTIER",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Commis de chantier"
    },
    {
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-ELECTRICIEN-BATIMENT",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Electricien bâtiment"
    },
    {
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-POSEUR-DE-PAVE",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Poseur de pavé"
    },
    {
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-MENUISIER-ALUMINIUM",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Menuisier aluminium"
    },
    {
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-AIDE-PLOMBIER",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Aide plombier"
    },
    {
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-PLATRIER",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Plâtrier"
    },
    {
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-CONDUCTEUR-DE-GRUE",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Conducteur de grue"
    },
    {
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-CONDUCTEUR-D-ENGIN",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Conducteur d'engin"
    },
    {
        "code": "TOURISME-HOTELLERIE-RESTAURATION-HOTELLERIE-CONCIERGE-D-HOTEL",
        "secteur": "Tourisme - Hôtellerie - Restauration",
        "filiere": "HOTELLERIE",
        "metier": "CONCIERGE D'HOTEL"
    },
    {
        "code": "TOURISME-HOTELLERIE-RESTAURATION-HOTELLERIE-AGENT-D-ACCUEIL",
        "secteur": "Tourisme - Hôtellerie - Restauration",
        "filiere": "HOTELLERIE",
        "metier": "AGENT D'ACCUEIL"
    },
    {
        "code": "TOURISME-HOTELLERIE-RESTAURATION-HOTELLERIE-HOTESSE-DE-SALLE",
        "secteur": "Tourisme - Hôtellerie - Restauration",
        "filiere": "HOTELLERIE",
        "metier": "HOTESSE DE SALLE"
    },
    {
        "code": "TEXTILE-HABILLEMENT-ACCESSOIRES-COUPE-ET-COUTURE-COUTURIER-E",
        "secteur": "Textile - Habillement - Accessoires",
        "filiere": "COUPE ET COUTURE",
        "metier": "COUTURIER (E)"
    },
    {
        "code": "ART-ET-TECHNIQUE-COIFFURE-AIDE-COFFEUSE",
        "secteur": "Art et Technique",
        "filiere": "COIFFURE",
        "metier": "AIDE COFFEUSE"
    },
    {
        "code": "TEXTILE-HABILLEMENT-ACCESSOIRES-BRODERIE-BRODEUR-BRODEUSE",
        "secteur": "Textile - Habillement - Accessoires",
        "filiere": "BRODERIE",
        "metier": "BRODEUR / BRODEUSE"
    },
    {
        "code": "TOURISME-HOTELLERIE-RESTAURATION-RESTAURATION-COMMIS-DE-CUISINE",
        "secteur": "Tourisme - Hôtellerie - Restauration",
        "filiere": "RESTAURATION",
        "metier": "COMMIS DE CUISINE"
    },
    {
        "code": "INDUSTRIEL-MAINTENANCE-INDUSTRIELLE-MAINTENANCIER-INDUSTRIEL",
        "secteur": "Industriel",
        "filiere": "MAINTENANCE INDUSTRIELLE",
        "metier": "Maintenancier industriel"
    },
    {
        "code": "INDUSTRIEL-STRUCTURE-METALLIQUE-TECHNICIEN-EN-OUVRAGE-METALLIQUE",
        "secteur": "Industriel",
        "filiere": "STRUCTURE METALLIQUE",
        "metier": "Technicien en ouvrage métallique"
    },
    {
        "code": "INDUSTRIEL-MECANIQUE-GENERALE-MECANICIEN-AUTO-MOTO",
        "secteur": "Industriel",
        "filiere": "MECANIQUE GENERALE",
        "metier": "Mécanicien auto moto"
    },
    {
        "code": "INDUSTRIEL-MECANIQUE-GENERALE-TECHNICIEN-METAUX-EN-FEUILLE",
        "secteur": "Industriel",
        "filiere": "MECANIQUE GENERALE",
        "metier": "Technicien métaux en feuille"
    },
    {
        "code": "MECANICIEN-D-AUTOMOBILES",
        "secteur": None,
        "filiere": None,
        "metier": "Mécanicien d’automobiles"
    },
    {
        "code": "DEVELOPPEMENT-RURAL-AGRICULTURE-AGENT-D-AGRICULTURE",
        "secteur": "Developpement Rural",
        "filiere": "AGRICULTURE",
        "metier": "AGENT D'AGRICULTURE"
    },
    {
        "code": "DEVELOPPEMENT-RURAL-ELEVAGE-TECHNICIEN-D-ELEVAGE",
        "secteur": "Developpement Rural",
        "filiere": "ELEVAGE",
        "metier": "TECHNICIEN D'ELEVAGE"
    },
    {
        "code": "GESTION-MANAGEMENT-ET-GESTION-D-ENTREPRISE-TECHNICIEN-SUPERIEUR-EN-MANAGEMENT-ET-GESTION-D-ENTREPRISE",
        "secteur": "Gestion",
        "filiere": "MANAGEMENT ET GESTION D'ENTREPRISE",
        "metier": "TECHNICIEN SUPERIEUR EN MANAGEMENT ET GESTION D'ENTREPRISE"
    },
    {
        "code": "INDUSTRIEL-GENIE-INDUSTRIEL-ET-ENERGIE-RENOUVELABLE-TECHNICIEN-EN-GENIE-INDUSTRIEL",
        "secteur": "Industriel",
        "filiere": "GENIE INDUSTRIEL ET ENERGIE RENOUVELABLE",
        "metier": "Technicien en génie industriel"
    },
    {
        "code": "DEVELOPPEMENT-RURAL-ELEVAGE-AVICULTEUR",
        "secteur": "Developpement Rural",
        "filiere": "ELEVAGE",
        "metier": "AVICULTEUR"
    },
    {
        "code": "PRODUCTEUR-DE-LEGUMES",
        "secteur": None,
        "filiere": None,
        "metier": "Producteur de légumes"
    },
    {
        "code": "RESTAURATEUR-DE-MEUBLES",
        "secteur": None,
        "filiere": None,
        "metier": "Restaurateur de meubles"
    },
    {
        "code": "INDUSTRIEL-IMPRIMERIE-TECHNICIEN-EN-IMPRIMERIE",
        "secteur": "Industriel",
        "filiere": "IMPRIMERIE",
        "metier": "Technicien en imprimerie"
    },
    {
        "code": "TECHNOLOGUE-EN-EQUIPEMENTS-AUDIOVISUELS",
        "secteur": None,
        "filiere": None,
        "metier": "Technologue en équipements audiovisuels"
    },
    {
        "code": "JARDINIER-PAYSAGISTE",
        "secteur": None,
        "filiere": None,
        "metier": "Jardinier paysagiste"
    }
]

ETABLISSEMENTS = [
    {
        "nom": "CFP FOULPOINTE",
        "region": "ATSINANANA",
        "type": "centre_formation",
        "commune": "Foulpointe",
        "keys": [
            "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-MENUSIER-EN-BOIS",
            "TOURISME-HOTELLERIE-RESTAURATION-HOTELLERIE-FEMME-VALET-DE-CHAMBRE",
            "TOURISME-HOTELLERIE-RESTAURATION-HOTELLERIE-BARMAN",
            "TOURISME-HOTELLERIE-RESTAURATION-RESTAURATION-PATISSIER",
            "CUISINIER",
            "TRAITEUR",
            "RESTAURATEUR-DE-MEUBLES"
        ]
    },
    {
        "nom": "LTP BERAVINA",
        "region": "HAUTE MATSIATRA",
        "type": "lycee_technique",
        "commune": None,
        "keys": [
            "GESTION-GESTION-COMPTABLE-AGENT-COMPTABLE",
            "INDUSTRIEL-FABRICATION-MECANIQUE-FRAISEUR",
            "INDUSTRIEL-ELECTRONIQUE-ELECTRONICIEN",
            "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-CHEF-D-EQUIPE-DE-CHANTIER",
            "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-DISSANATEUR-PROJETEUR-METREUR",
            "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-CARRELEUR",
            "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-ARCHITECTE",
            "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-DECORATEUR-D-INTERIEUR",
            "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-TOPOGRAPHE",
            "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-COMMIS-DE-CHANTIER",
            "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-MENUSIER-EN-BOIS",
            "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-ELECTRICIEN-BATIMENT",
            "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-POSEUR-DE-PAVE",
            "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-MENUISIER-ALUMINIUM",
            "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-AIDE-PLOMBIER",
            "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-PLATRIER",
            "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-CONDUCTEUR-DE-GRUE",
            "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-CONDUCTEUR-D-ENGIN",
            "TOURISME-HOTELLERIE-RESTAURATION-HOTELLERIE-FEMME-VALET-DE-CHAMBRE",
            "TOURISME-HOTELLERIE-RESTAURATION-HOTELLERIE-CONCIERGE-D-HOTEL",
            "TOURISME-HOTELLERIE-RESTAURATION-HOTELLERIE-AGENT-D-ACCUEIL",
            "TOURISME-HOTELLERIE-RESTAURATION-HOTELLERIE-HOTESSE-DE-SALLE",
            "TOURISME-HOTELLERIE-RESTAURATION-HOTELLERIE-BARMAN"
        ]
    },
    {
        "nom": "LTP ANKAZOBE",
        "region": "ANALAMANGA",
        "type": "lycee_technique",
        "commune": "Ankazobe",
        "keys": [
            "GESTION-GESTION-COMPTABLE-AGENT-COMPTABLE",
            "TEXTILE-HABILLEMENT-ACCESSOIRES-COUPE-ET-COUTURE-COUTURIER-E",
            "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-CHEF-D-EQUIPE-DE-CHANTIER",
            "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-MENUSIER-EN-BOIS"
        ]
    },
    {
        "nom": "CFP MASINDRAY",
        "region": "ANALAMANGA",
        "type": "centre_formation",
        "commune": "Masindray",
        "keys": [
            "TEXTILE-HABILLEMENT-ACCESSOIRES-COUPE-ET-COUTURE-COUTURIER-E",
            "ART-ET-TECHNIQUE-COIFFURE-AIDE-COFFEUSE",
            "TEXTILE-HABILLEMENT-ACCESSOIRES-BRODERIE-BRODEUR-BRODEUSE",
            "TOURISME-HOTELLERIE-RESTAURATION-RESTAURATION-COMMIS-DE-CUISINE",
            "JARDINIER-PAYSAGISTE"
        ]
    },
    {
        "nom": "CFP AMPASAMPITO",
        "region": "ANALAMANGA",
        "type": "centre_formation",
        "commune": "Ampasampito",
        "keys": [
            "INDUSTRIEL-IMPRIMERIE-TECHNICIEN-EN-IMPRIMERIE"
        ]
    },
    {
        "nom": "LTP ALAROBIA",
        "region": "ANALAMANGA",
        "type": "lycee_technique",
        "commune": "Alarobia",
        "keys": [
            "INDUSTRIEL-FABRICATION-MECANIQUE-FRAISEUR",
            "INDUSTRIEL-MAINTENANCE-INDUSTRIELLE-MAINTENANCIER-INDUSTRIEL",
            "TECHNOLOGUE-EN-EQUIPEMENTS-AUDIOVISUELS"
        ]
    },
    {
        "nom": "LTP AMPASAPITO",
        "region": "ANALAMANGA",
        "type": "lycee_technique",
        "commune": "Ampasapito",
        "keys": [
            "INDUSTRIEL-STRUCTURE-METALLIQUE-TECHNICIEN-EN-OUVRAGE-METALLIQUE",
            "INDUSTRIEL-MECANIQUE-GENERALE-MECANICIEN-AUTO-MOTO",
            "INDUSTRIEL-MECANIQUE-GENERALE-TECHNICIEN-METAUX-EN-FEUILLE",
            "MECANICIEN-D-AUTOMOBILES"
        ]
    },
    {
        "nom": "LTP ANKAZONDANDY",
        "region": "ANALAMANGA",
        "type": "lycee_technique",
        "commune": "Ankazondandy",
        "keys": [
            "DEVELOPPEMENT-RURAL-AGRICULTURE-AGENT-D-AGRICULTURE",
            "DEVELOPPEMENT-RURAL-ELEVAGE-TECHNICIEN-D-ELEVAGE",
            "GESTION-GESTION-COMPTABLE-AGENT-COMPTABLE",
            "GESTION-MANAGEMENT-ET-GESTION-D-ENTREPRISE-TECHNICIEN-SUPERIEUR-EN-MANAGEMENT-ET-GESTION-D-ENTREPRISE",
            "INDUSTRIEL-GENIE-INDUSTRIEL-ET-ENERGIE-RENOUVELABLE-TECHNICIEN-EN-GENIE-INDUSTRIEL",
            "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-POSEUR-DE-PAVE",
            "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-MENUISIER-ALUMINIUM",
            "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-AIDE-PLOMBIER",
            "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-PLATRIER",
            "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-CONDUCTEUR-DE-GRUE",
            "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-CONDUCTEUR-D-ENGIN"
        ]
    },
    {
        "nom": "LTP FARATSIHO",
        "region": "VAKINANKARATRA",
        "type": "lycee_technique",
        "commune": "Faratsiho",
        "keys": [
            "DEVELOPPEMENT-RURAL-AGRICULTURE-AGENT-D-AGRICULTURE",
            "DEVELOPPEMENT-RURAL-ELEVAGE-TECHNICIEN-D-ELEVAGE",
            "GESTION-GESTION-COMPTABLE-AGENT-COMPTABLE",
            "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-CHEF-D-EQUIPE-DE-CHANTIER"
        ]
    },
    {
        "nom": "CFP ANKAZOMIRIOTRA",
        "region": "VAKINANKARATRA",
        "type": "centre_formation",
        "commune": "Ankazomiriotra",
        "keys": [
            "INDUSTRIEL-STRUCTURE-METALLIQUE-TECHNICIEN-EN-OUVRAGE-METALLIQUE",
            "TEXTILE-HABILLEMENT-ACCESSOIRES-COUPE-ET-COUTURE-COUTURIER-E",
            "TEXTILE-HABILLEMENT-ACCESSOIRES-BRODERIE-BRODEUR-BRODEUSE",
            "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-CHEF-D-EQUIPE-DE-CHANTIER",
            "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-COMMIS-DE-CHANTIER",
            "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-MENUSIER-EN-BOIS"
        ]
    },
    {
        "nom": "LTP MANDOTO",
        "region": "VAKINANKARATRA",
        "type": "lycee_technique",
        "commune": "Mandoto",
        "keys": [
            "DEVELOPPEMENT-RURAL-AGRICULTURE-AGENT-D-AGRICULTURE",
            "DEVELOPPEMENT-RURAL-ELEVAGE-TECHNICIEN-D-ELEVAGE",
            "GESTION-GESTION-COMPTABLE-AGENT-COMPTABLE",
            "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-CHEF-D-EQUIPE-DE-CHANTIER",
            "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-POSEUR-DE-PAVE",
            "DEVELOPPEMENT-RURAL-ELEVAGE-AVICULTEUR",
            "PRODUCTEUR-DE-LEGUMES"
        ]
    }
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

    chemin_ids = {}
    for parcours in PARCOURS:
        existing = conn.execute(
            sa.text("SELECT id FROM parcourstechniqueprofessionnel WHERE code=:code"),
            {"code": parcours["code"]},
        ).first()
        if existing:
            chemin_ids[parcours["code"]] = int(existing[0])
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
        chemin_ids[parcours["code"]] = int(conn.execute(
            sa.text("SELECT id FROM parcourstechniqueprofessionnel WHERE code=:code"),
            {"code": parcours["code"]},
        ).scalar_one())

    for etablissement in ETABLISSEMENTS:
        nom = etablissement["nom"]
        region = etablissement["region"]
        row = conn.execute(
            sa.text(
                "SELECT id FROM etablissementscolaire WHERE lower(trim(nom))=lower(trim(:nom)) "
                "AND lower(trim(coalesce(region, '')))=lower(trim(:region))"
            ),
            {"nom": nom, "region": region},
        ).first()

        empreinte = hashlib.sha1(f"{region}|{nom}".encode("utf-8")).hexdigest()[:6].upper()
        code_etablissement = f"METFP-{_slug(region)[:10]}-{_slug(nom)[:14]}-{empreinte}"
        if row:
            etablissement_id = int(row[0])
            conn.execute(
                sa.text(
                    "UPDATE etablissementscolaire SET "
                    "code=coalesce(code, :code), type_etablissement=:type, "
                    "commune=coalesce(commune, :commune), source_officielle=:source, "
                    "est_verifie=TRUE, est_actif=TRUE, date_maj=:updated WHERE id=:id"
                ),
                {
                    "code": code_etablissement,
                    "type": etablissement["type"],
                    "commune": etablissement["commune"],
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
                    "VALUES (:nom, :code, :type, 'inconnu', :region, NULL, :commune, "
                    ":source, TRUE, TRUE, :created, :updated)"
                ),
                {
                    "nom": nom,
                    "code": code_etablissement,
                    "type": etablissement["type"],
                    "region": region,
                    "commune": etablissement["commune"],
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
                {"nom": nom, "region": region},
            ).scalar_one())

        # Les offres restent en attente tant que l'année et la réalité locale n'ont pas été confirmées.
        for code_parcours in etablissement["keys"]:
            chemin_id = chemin_ids.get(code_parcours)
            if chemin_id is None:
                raise RuntimeError(f"Parcours officiel absent avant l'ajout de l'offre : {code_parcours}")

            code_offre = "FORMATION:" + _slug(code_parcours)
            existe = conn.execute(
                sa.text(
                    "SELECT id FROM offreetablissementscolaire "
                    "WHERE etablissement_id=:etablissement AND code_offre=:code "
                    "AND annee_scolaire IS NULL AND est_active=TRUE"
                ),
                {"etablissement": etablissement_id, "code": code_offre},
            ).first()
            if existe:
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
                    "parcours": chemin_id,
                    "source": SOURCE_CARTOGRAPHIE,
                    "created": maintenant,
                    "updated": maintenant,
                },
            )


def downgrade() -> None:
    # Ne pas détruire une offre qui aurait été complétée et validée manuellement.
    # Les données d'inventaire sont conservées pour préserver l'historique.
    pass
