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
        "secteur": null,
        "filiere": null,
        "metier": "Cuisinier"
    },
    {
        "code": "TRAITEUR",
        "secteur": null,
        "filiere": null,
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
        "code": "RESTAURATEUR-DE-MEUBLES",
        "secteur": null,
        "filiere": null,
        "metier": "Restaurateur de meubles"
    }
]

ETABLISSEMENTS = [
    {
        "nom": "CFP FOULPOINTE",
        "region": "ATSINANANA",
        "type": "centre_formation",
        "commune": "Foulpointe",
        "keys": [
            "BTPMENUISIER",
            "HOTEL_FEMME_CHAMBRE",
            "HOTEL_BARMAN",
            "RESTO_PATISSIER",
            "METIER_CUISINIER",
            "RESTO_TRAITEUR",
            "RESTAURATEUR-DE-MEUBLES"
        ]
    },
    {
        "nom": "LTP BERAVINA",
        "region": "HAUTE MATSIATRA",
        "type": "lycee_technique",
        "commune": null,
        "keys": [
            "GESTION_COMPTABLE",
            "INDFRAISEUR",
            "INDELECTRONIQUE",
            "BTPCHEF",
            "BTPDESSIN",
            "BTPCARRELEUR",
            "BTPARCHITECTE",
            "BTPDECORATEUR",
            "BTPTOPGRAPHE",
            "BTPCOMMIS",
            "BTPMENUISIER",
            "BTPELECTRICIEN",
            "BTPPOSEUR",
            "BTPALUMINIUM",
            "BTPPLOMBIER",
            "BTPPLATRIER",
            "BTPCONDUCTEUR_GRUE",
            "BTPCONDUCTEUR_ENGIN",
            "HOTEL_FEMME_CHAMBRE",
            "HOTEL_CONCIERGE",
            "HOTEL_AGENT_ACCUEIL",
            "HOTEL_HOTESSE_SALLE",
            "HOTEL_BARMAN"
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
            if code_parcours == "RESTAURATEUR-DE-MEUBLES":
                chemin_id = chemin_ids[code_parcours]
            else:
                # Les codes historiques sont construits depuis le triplet officiel normalisé.
                chemin_id = conn.execute(
                    sa.text(
                        "SELECT id FROM parcourstechniqueprofessionnel WHERE code=:code"
                    ),
                    {"code": next(p["code"] for p in PARCOURS if p["code"] == _slug("-".join(
                        part for part in (
                            next(x["secteur"] for x in PARCOURS if x["code"] == next(
                                y["code"] for y in PARCOURS if y["code"] == code_parcours
                            )),
                        ) if part
                    )))},
                ).scalar() if False else None

            # All pathway IDs are cached by normalized code.
            if chemin_id is None:
                chemin_id = conn.execute(
                    sa.text("SELECT id FROM parcourstechniqueprofessionnel WHERE code=:code"),
                    {"code": code_parcours},
                ).scalar()
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
