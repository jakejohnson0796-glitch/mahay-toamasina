"""Réconcilie les établissements et métiers ETFP confirmés dans la cartographie METFP.

Revision ID: e3b9c6a1d740
Revises: d2a7c5e9f840

Migration additive et idempotente : les établissements sont des entrées vérifiées
du répertoire officiel, mais les offres restent sans année scolaire et à vérifier
tant que l'ouverture locale de la formation n'a pas été confirmée.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime

from alembic import op
import sqlalchemy as sa

revision = "e3b9c6a1d740"
down_revision = "d2a7c5e9f840"
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
        "code": "TEXTILE-HABILLEMENT-ACCESSOIRES-COUPE-ET-COUTURE-COUTURIER-E",
        "secteur": "Textile - Habillement - Accessoires",
        "filiere": "COUPE ET COUTURE",
        "metier": "COUTURIER (E)",
    },
    {
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-CHEF-D-EQUIPE-DE-CHANTIER",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Chef d'Equipe de chantier",
    },
    {
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-MENUSIER-EN-BOIS",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Menusier en bois",
    },
    {
        "code": "DEVELOPPEMENT-RURAL-ELEVAGE-TECHNICIEN-D-ELEVAGE",
        "secteur": "Developpement Rural",
        "filiere": "ELEVAGE",
        "metier": "TECHNICIEN D'ELEVAGE",
    },
    {
        "code": "ART-ET-TECHNIQUE-COIFFURE-AIDE-COFFEUSE",
        "secteur": "Art et Technique",
        "filiere": "COIFFURE",
        "metier": "AIDE COFFEUSE",
    },
    {
        "code": "TEXTILE-HABILLEMENT-ACCESSOIRES-BRODERIE-BRODEUR-BRODEUSE",
        "secteur": "Textile - Habillement - Accessoires",
        "filiere": "BRODERIE",
        "metier": "BRODEUR / BRODEUSE",
    },
    {
        "code": "TOURISME-HOTELLERIE-RESTAURATION-RESTAURATION-COMMIS-DE-CUISINE",
        "secteur": "Tourisme - Hôtellerie - Restauration",
        "filiere": "RESTAURATION",
        "metier": "COMMIS DE CUISINE",
    },
    {
        "code": "JARDINIER-PAYSAGISTE",
        "secteur": None,
        "filiere": None,
        "metier": "Jardinier paysagiste",
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
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-DISSANATEUR-PROJETEUR-METREUR",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Dissanateur Projeteur Métreur",
    },
    {
        "code": "TOURISME-HOTELLERIE-RESTAURATION-RESTAURATION-PATISSIER",
        "secteur": "Tourisme - Hôtellerie - Restauration",
        "filiere": "RESTAURATION",
        "metier": "PATISSIER",
    },
    {
        "code": "PRODUCTEUR-DE-LEGUMES",
        "secteur": None,
        "filiere": None,
        "metier": "Producteur de légumes",
    },
    {
        "code": "INDUSTRIEL-STRUCTURE-METALLIQUE-TECHNICIEN-EN-OUVRAGE-METALLIQUE",
        "secteur": "Industriel",
        "filiere": "STRUCTURE METALLIQUE",
        "metier": "Technicien en ouvrage métallique",
    },
    {
        "code": "CUISINIER",
        "secteur": None,
        "filiere": None,
        "metier": "Cuisinier",
    },
    {
        "code": "TOURISME-HOTELLERIE-RESTAURATION-TOURISME-ACCOMPAGNATEUR-TOURISTIQUE",
        "secteur": "Tourisme - Hôtellerie - Restauration",
        "filiere": "TOURISME",
        "metier": "ACCOMPAGNATEUR TOURISTIQUE",
    },
    {
        "code": "DEVELOPPEMENT-RURAL-AGRICULTURE-AGENT-D-AGRICULTURE",
        "secteur": "Developpement Rural",
        "filiere": "AGRICULTURE",
        "metier": "AGENT D'AGRICULTURE",
    },
    {
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-COMMIS-DE-CHANTIER",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Commis de chantier",
    },
    {
        "code": "GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-POSEUR-DE-PAVE",
        "secteur": "Genie Civil",
        "filiere": "Batiment et Travaux Public",
        "metier": "Poseur de pavé",
    },
    {
        "code": "BOULANGER-PATISSIER",
        "secteur": None,
        "filiere": None,
        "metier": "Boulanger-pâtissier",
    },
]

ETABLISSEMENTS = [
    {
        "nom": "LTP ANKAZOBE",
        "region": "ANALAMANGA",
        "type": "lycee_technique",
        "commune": "Ankazobe",
        "keys": ["GESTION-GESTION-COMPTABLE-AGENT-COMPTABLE","TEXTILE-HABILLEMENT-ACCESSOIRES-COUPE-ET-COUTURE-COUTURIER-E","GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-CHEF-D-EQUIPE-DE-CHANTIER","GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-MENUSIER-EN-BOIS"],
    },
    {
        "nom": "LTP SOAVINA",
        "region": "ANALAMANGA",
        "type": "lycee_technique",
        "commune": "Soavina",
        "keys": ["DEVELOPPEMENT-RURAL-ELEVAGE-TECHNICIEN-D-ELEVAGE","GESTION-GESTION-COMPTABLE-AGENT-COMPTABLE","GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-CHEF-D-EQUIPE-DE-CHANTIER"],
    },
    {
        "nom": "CFP MASINDRAY",
        "region": "ANALAMANGA",
        "type": "centre_formation",
        "commune": "Masindray",
        "keys": ["TEXTILE-HABILLEMENT-ACCESSOIRES-COUPE-ET-COUTURE-COUTURIER-E","ART-ET-TECHNIQUE-COIFFURE-AIDE-COFFEUSE","TEXTILE-HABILLEMENT-ACCESSOIRES-BRODERIE-BRODEUR-BRODEUSE","TOURISME-HOTELLERIE-RESTAURATION-RESTAURATION-COMMIS-DE-CUISINE","JARDINIER-PAYSAGISTE"],
    },
    {
        "nom": "LTP ALAROBIA AMBATOMANGA",
        "region": "ANALAMANGA",
        "type": "lycee_technique",
        "commune": "Alarobia Ambatomanga",
        "keys": ["DEVELOPPEMENT-RURAL-ELEVAGE-TECHNICIEN-D-ELEVAGE","GESTION-GESTION-COMPTABLE-AGENT-COMPTABLE","GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-CHEF-D-EQUIPE-DE-CHANTIER"],
    },
    {
        "nom": "LTP MANJAKANDRIANA",
        "region": "ANALAMANGA",
        "type": "lycee_technique",
        "commune": "Manjakandriana",
        "keys": ["DEVELOPPEMENT-RURAL-ELEVAGE-ELEVEUR-DE-PORC","DEVELOPPEMENT-RURAL-ELEVAGE-AVICULTEUR","GESTION-GESTION-COMPTABLE-AGENT-COMPTABLE","TEXTILE-HABILLEMENT-ACCESSOIRES-COUPE-ET-COUTURE-COUTURIER-E","GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-CHEF-D-EQUIPE-DE-CHANTIER","GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-DISSANATEUR-PROJETEUR-METREUR","TOURISME-HOTELLERIE-RESTAURATION-RESTAURATION-PATISSIER","PRODUCTEUR-DE-LEGUMES"],
    },
    {
        "nom": "LTP MANTASOA",
        "region": "ANALAMANGA",
        "type": "lycee_technique",
        "commune": "Mantasoa",
        "keys": ["INDUSTRIEL-STRUCTURE-METALLIQUE-TECHNICIEN-EN-OUVRAGE-METALLIQUE","GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-CHEF-D-EQUIPE-DE-CHANTIER"],
    },
    {
        "nom": "CFPF ANTSOFINONDRY SABOTSY NAMEHENA",
        "region": "ANALAMANGA",
        "type": "centre_formation_specialise",
        "commune": "Sabotsy Namehana",
        "keys": ["TEXTILE-HABILLEMENT-ACCESSOIRES-COUPE-ET-COUTURE-COUTURIER-E","TEXTILE-HABILLEMENT-ACCESSOIRES-BRODERIE-BRODEUR-BRODEUSE","JARDINIER-PAYSAGISTE","CUISINIER"],
    },
    {
        "nom": "LT AMPEFILOHA - LTA (EX-CTM)",
        "region": "ANALAMANGA",
        "type": "lycee_technique",
        "commune": "Antananarivo",
        "keys": ["TEXTILE-HABILLEMENT-ACCESSOIRES-COUPE-ET-COUTURE-COUTURIER-E","TOURISME-HOTELLERIE-RESTAURATION-RESTAURATION-PATISSIER","TOURISME-HOTELLERIE-RESTAURATION-TOURISME-ACCOMPAGNATEUR-TOURISTIQUE"],
    },
    {
        "nom": "LTP AMPEFILOHA",
        "region": "ANALAMANGA",
        "type": "lycee_technique",
        "commune": "Antananarivo",
        "keys": ["GESTION-GESTION-COMPTABLE-AGENT-COMPTABLE"],
    },
    {
        "nom": "CFPF TSIMBAZAZA",
        "region": "ANALAMANGA",
        "type": "centre_formation_specialise",
        "commune": "Antananarivo",
        "keys": ["ART-ET-TECHNIQUE-COIFFURE-AIDE-COFFEUSE","TEXTILE-HABILLEMENT-ACCESSOIRES-COUPE-ET-COUTURE-COUTURIER-E","TEXTILE-HABILLEMENT-ACCESSOIRES-BRODERIE-BRODEUR-BRODEUSE","TOURISME-HOTELLERIE-RESTAURATION-RESTAURATION-COMMIS-DE-CUISINE","JARDINIER-PAYSAGISTE"],
    },
    {
        "nom": "LTP FARATSIHO",
        "region": "VAKINANKARATRA",
        "type": "lycee_technique",
        "commune": "Faratsiho",
        "keys": ["DEVELOPPEMENT-RURAL-AGRICULTURE-AGENT-D-AGRICULTURE","DEVELOPPEMENT-RURAL-ELEVAGE-TECHNICIEN-D-ELEVAGE","GESTION-GESTION-COMPTABLE-AGENT-COMPTABLE","GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-CHEF-D-EQUIPE-DE-CHANTIER"],
    },
    {
        "nom": "CFP ANKAZOMIRIOTRA",
        "region": "VAKINANKARATRA",
        "type": "centre_formation",
        "commune": "Ankazomiriotra",
        "keys": ["INDUSTRIEL-STRUCTURE-METALLIQUE-TECHNICIEN-EN-OUVRAGE-METALLIQUE","TEXTILE-HABILLEMENT-ACCESSOIRES-COUPE-ET-COUTURE-COUTURIER-E","TEXTILE-HABILLEMENT-ACCESSOIRES-BRODERIE-BRODEUR-BRODEUSE","GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-CHEF-D-EQUIPE-DE-CHANTIER","GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-COMMIS-DE-CHANTIER","GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-MENUSIER-EN-BOIS"],
    },
    {
        "nom": "LTP MANDOTO",
        "region": "VAKINANKARATRA",
        "type": "lycee_technique",
        "commune": "Mandoto",
        "keys": ["DEVELOPPEMENT-RURAL-AGRICULTURE-AGENT-D-AGRICULTURE","DEVELOPPEMENT-RURAL-ELEVAGE-TECHNICIEN-D-ELEVAGE","GESTION-GESTION-COMPTABLE-AGENT-COMPTABLE","GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-CHEF-D-EQUIPE-DE-CHANTIER","GENIE-CIVIL-BATIMENT-ET-TRAVAUX-PUBLIC-POSEUR-DE-PAVE","DEVELOPPEMENT-RURAL-ELEVAGE-AVICULTEUR","PRODUCTEUR-DE-LEGUMES"],
    },
]

# Ces deux métiers figurent explicitement dans la cartographie de CFP Foulpointe,
# mais n'étaient pas encore rattachés à une offre de ce centre dans la migration d2.
OFFRES_SUPPLEMENTAIRES_FOULPOINTE = [
    "TOURISME-HOTELLERIE-RESTAURATION-RESTAURATION-RESTAURATEUR-VILLAGEOIS",
    "BOULANGER-PATISSIER",
]


def _slug(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").upper()
    return value[:120] or "SANS-CODE"


def _chemin_id(conn, code: str) -> int:
    identifiant = conn.execute(
        sa.text("SELECT id FROM parcourstechniqueprofessionnel WHERE code=:code"),
        {"code": code},
    ).scalar()
    if identifiant is None:
        raise RuntimeError(f"Le parcours ETFP nécessaire est absent du référentiel : {code}")
    return int(identifiant)


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
            {
                **parcours,
                "source": SOURCE_CARTOGRAPHIE,
                "created": maintenant,
                "updated": maintenant,
            },
        )


def _assurer_offre(conn, etablissement_id: int, code_parcours: str, maintenant: datetime) -> None:
    parcours_id = _chemin_id(conn, code_parcours)
    code_offre = "FORMATION:" + _slug(code_parcours)
    existe = conn.execute(
        sa.text(
            "SELECT id FROM offreetablissementscolaire WHERE etablissement_id=:etablissement "
            "AND code_offre=:code AND annee_scolaire IS NULL AND est_active=TRUE"
        ),
        {"etablissement": etablissement_id, "code": code_offre},
    ).first()
    if existe:
        return
    conn.execute(
        sa.text(
            "INSERT INTO offreetablissementscolaire "
            "(etablissement_id, code_offre, type_offre, niveau_scolaire_id, option_scolaire_id, "
            "matiere_scolaire_id, parcours_etfp_id, annee_scolaire, source_officielle, "
            "statut_validation, est_active, date_creation, date_maj) "
            "VALUES (:etablissement, :code, 'formation', NULL, NULL, NULL, :parcours, NULL, "
            ":source, 'a_verifier', TRUE, :created, :updated)"
        ),
        {
            "etablissement": etablissement_id,
            "code": code_offre,
            "parcours": parcours_id,
            "source": SOURCE_CARTOGRAPHIE,
            "created": maintenant,
            "updated": maintenant,
        },
    )


def _assurer_etablissement(conn, site: dict, maintenant: datetime) -> int:
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
        "code": code,
        "nom": nom,
        "region": region,
        "type": site["type"],
        "commune": site["commune"],
        "source": SOURCE_CARTOGRAPHIE,
        "created": maintenant,
        "updated": maintenant,
    }
    if existant:
        identifiant = int(existant[0])
        conn.execute(
            sa.text(
                "UPDATE etablissementscolaire SET code=coalesce(code, :code), "
                "type_etablissement=:type, commune=coalesce(commune, :commune), "
                "source_officielle=:source, est_verifie=TRUE, est_actif=TRUE, date_maj=:updated "
                "WHERE id=:id"
            ),
            {**params, "id": identifiant},
        )
        return identifiant
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
    return int(conn.execute(
        sa.text(
            "SELECT id FROM etablissementscolaire WHERE lower(trim(nom))=lower(trim(:nom)) "
            "AND lower(trim(coalesce(region, '')))=lower(trim(:region))"
        ),
        {"nom": nom, "region": region},
    ).scalar_one())


def upgrade() -> None:
    conn = op.get_bind()
    maintenant = datetime.utcnow()
    _assurer_parcours(conn, maintenant)

    for site in ETABLISSEMENTS:
        etablissement_id = _assurer_etablissement(conn, site, maintenant)
        for code_parcours in sorted(set(site["keys"])):
            _assurer_offre(conn, etablissement_id, code_parcours, maintenant)

    # Complète les deux métiers publics manquants de CFP Foulpointe sans dupliquer les 7 offres
    # déjà importées par d2a7c5e9f840. Aucun nouveau millésime n'est présumé.
    foulpointe = conn.execute(
        sa.text(
            "SELECT id FROM etablissementscolaire WHERE lower(trim(nom))=lower(trim('CFP FOULPOINTE')) "
            "AND lower(trim(coalesce(region, '')))=lower(trim('ATSINANANA'))"
        )
    ).scalar()
    if foulpointe is not None:
        for code_parcours in OFFRES_SUPPLEMENTAIRES_FOULPOINTE:
            _assurer_offre(conn, int(foulpointe), code_parcours, maintenant)


def downgrade() -> None:
    # Les enregistrements peuvent avoir été revus/complétés par un administrateur.
    # Ne pas supprimer automatiquement des établissements ou offres historiques.
    pass
