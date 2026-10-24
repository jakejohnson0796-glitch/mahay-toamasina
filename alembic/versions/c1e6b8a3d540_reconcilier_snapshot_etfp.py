"""Réconcilie les données ETFP ajoutées au snapshot après la première application.

Revision ID: c1e6b8a3d540
Revises: b7d4e9c2a610

Le service de prévisualisation a appliqué le snapshot initial avant que quatre
établissements et trois libellés officiels aient été ajoutés au code. Cette
migration additive et idempotente réconcilie les données déjà présentes en
production sans rejouer ni modifier la migration historique. Les offres créées
restent « a_verifier » et sans année scolaire confirmée.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime

from alembic import op
import sqlalchemy as sa

revision = "c1e6b8a3d540"
down_revision = "b7d4e9c2a610"
branch_labels = None
depends_on = None

SOURCE_CARTOGRAPHIE = "https://www.metfp.gov.mg/cartographie"

# Code clé -> triplet secteur/filière/métier tel que normalisé par b7d4e9c2a610.
PATHES_ETFP = {
    "BTPCHEF": [
        "Genie Civil",
        "Batiment et Travaux Public",
        "Chef d'Equipe de chantier"
    ],
    "BTPDESSIN": [
        "Genie Civil",
        "Batiment et Travaux Public",
        "Dissanateur Projeteur Métreur"
    ],
    "BTPCARRELEUR": [
        "Genie Civil",
        "Batiment et Travaux Public",
        "Carreleur"
    ],
    "BTPARCHITECTE": [
        "Genie Civil",
        "Batiment et Travaux Public",
        "Architecte"
    ],
    "BTPDECORATEUR": [
        "Genie Civil",
        "Batiment et Travaux Public",
        "Décorateur d'intérieur"
    ],
    "BTPTOPGRAPHE": [
        "Genie Civil",
        "Batiment et Travaux Public",
        "Topographe"
    ],
    "BTPCOMMIS": [
        "Genie Civil",
        "Batiment et Travaux Public",
        "Commis de chantier"
    ],
    "BTPMENUISIER": [
        "Genie Civil",
        "Batiment et Travaux Public",
        "Menusier en bois"
    ],
    "BTPELECTRICIEN": [
        "Genie Civil",
        "Batiment et Travaux Public",
        "Electricien bâtiment"
    ],
    "BTPPOSEUR": [
        "Genie Civil",
        "Batiment et Travaux Public",
        "Poseur de pavé"
    ],
    "BTPALUMINIUM": [
        "Genie Civil",
        "Batiment et Travaux Public",
        "Menuisier aluminium"
    ],
    "BTPPLOMBIER": [
        "Genie Civil",
        "Batiment et Travaux Public",
        "Aide plombier"
    ],
    "BTPPLATRIER": [
        "Genie Civil",
        "Batiment et Travaux Public",
        "Plâtrier"
    ],
    "BTPCONDUCTEUR_GRUE": [
        "Genie Civil",
        "Batiment et Travaux Public",
        "Conducteur de grue"
    ],
    "BTPCONDUCTEUR_ENGIN": [
        "Genie Civil",
        "Batiment et Travaux Public",
        "Conducteur d'engin"
    ],
    "INDSTRUCTURE": [
        "Industriel",
        "STRUCTURE METALLIQUE",
        "Technicien en ouvrage métallique"
    ],
    "INDMECANIQUE": [
        "Industriel",
        "MECANIQUE GENERALE",
        "Mécanicien auto moto"
    ],
    "GESTION_COMPTABLE": [
        "Gestion",
        "GESTION COMPTABLE",
        "AGENT COMPTABLE"
    ],
    "GESTION_ENTREPRISE": [
        "Gestion",
        "MANAGEMENT ET GESTION D'ENTREPRISE",
        "TECHNICIEN SUPERIEUR EN MANAGEMENT ET GESTION D'ENTREPRISE"
    ],
    "INDFRAISEUR": [
        "Industriel",
        "FABRICATION MECANIQUE",
        "Fraiseur"
    ],
    "INDMAINTENANCE": [
        "Industriel",
        "MAINTENANCE INDUSTRIELLE",
        "Maintenancier industriel"
    ],
    "AGRICULTURE_AGENT": [
        "Developpement Rural",
        "AGRICULTURE",
        "AGENT D'AGRICULTURE"
    ],
    "AGRICULTURE_MARAICHERE": [
        "Developpement Rural",
        "AGRICULTURE",
        "AGRICULTEUR MARAICHERE"
    ],
    "AGRICULTURE_EXPLOITANT": [
        "Developpement Rural",
        "AGRICULTURE",
        "EXPLOITANT AGRICOLE"
    ],
    "AGRICULTURE_JARDINIER": [
        "Developpement Rural",
        "AGRICULTURE",
        "JARDINIER PAYSAGISTE"
    ],
    "ELEVAGE_APICULTEUR": [
        "Developpement Rural",
        "ELEVAGE",
        "APICULTEUR"
    ]
}

# nom officiel, région, type, commune, métiers explicitement listés par la source.
ETABLISSEMENTS_A_AJOUTER = [
    [
        "CFP MAROATSETRA",
        "AMBATOSOA",
        "centre_formation",
        "Maroantsetra",
        [
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
            "BTPCONDUCTEUR_ENGIN"
        ]
    ],
    [
        "LTP AMBANJA",
        "DIANA",
        "lycee_technique",
        "Ambanja",
        []
    ],
    [
        "LTP TOLIARA",
        "ATSIMO ANDREFANA",
        "lycee_technique",
        "Toliara",
        [
            "INDSTRUCTURE",
            "INDMECANIQUE",
            "GESTION_COMPTABLE",
            "GESTION_ENTREPRISE",
            "INDFRAISEUR",
            "INDMAINTENANCE",
            "BTPCHEF",
            "BTPDESSIN",
            "BTPMENUISIER"
        ]
    ],
    [
        "CFP ROBSON TSIRAVOA DE MILENAKE",
        "ATSIMO ANDREFANA",
        "centre_formation",
        "Milenake",
        [
            "AGRICULTURE_AGENT",
            "AGRICULTURE_MARAICHERE",
            "AGRICULTURE_EXPLOITANT",
            "AGRICULTURE_JARDINIER",
            "ELEVAGE_APICULTEUR"
        ]
    ]
]

# Correction de présentation uniquement ; les identifiants et offres existants restent intacts.
RENOMMAGES = [
    [
        "CNFPPSH",
        "ANALAMANGA",
        "Centre National de Formation Professionnelle des Personnes en Situation de Handicap (CNFPPSH)"
    ],
    [
        "CRFPPV MIARY TOLIARA",
        "ATSIMO ANDREFANA",
        "Centre Régional de Formation Professionnelle des Personnes Vulnérables (CRFPPV) Miary Toliara"
    ],
    [
        "CRFPPV MAHAJANGA",
        "BOENY",
        "Centre Régional de Formation Professionnelle des Personnes Vulnérables (CRFPPV) Mahajanga"
    ]
]


def _slug(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").upper()
    return value[:120] or "SANS-CODE"


def _id_parcours(conn, code_cle: str) -> int:
    triple = PATHES_ETFP[code_cle]
    code = _slug("-".join(part for part in triple if part))
    identifiant = conn.execute(
        sa.text("SELECT id FROM parcourstechniqueprofessionnel WHERE code=:code"),
        {"code": code},
    ).scalar()
    if identifiant is None:
        raise RuntimeError(
            f"Le parcours ETFP requis est absent de la table normalisée : {code_cle} ({code})"
        )
    return int(identifiant)


def upgrade() -> None:
    conn = op.get_bind()
    maintenant = datetime.utcnow()

    # Renommer les trois entrées conservées, sans recréer les liens ni changer leur code.
    for ancien_nom, region, nom_officiel in RENOMMAGES:
        conn.execute(
            sa.text(
                "UPDATE etablissementscolaire "
                "SET nom=:nouveau, source_officielle=:source, date_maj=:updated "
                "WHERE lower(trim(nom))=lower(trim(:ancien)) "
                "AND lower(trim(coalesce(region, '')))=lower(trim(:region))"
            ),
            {
                "ancien": ancien_nom,
                "nouveau": nom_officiel,
                "region": region,
                "source": SOURCE_CARTOGRAPHIE,
                "updated": maintenant,
            },
        )

    for nom, region, type_etablissement, commune, codes_parcours in ETABLISSEMENTS_A_AJOUTER:
        ligne = conn.execute(
            sa.text(
                "SELECT id FROM etablissementscolaire "
                "WHERE lower(trim(nom))=lower(trim(:nom)) "
                "AND lower(trim(coalesce(region, '')))=lower(trim(:region))"
            ),
            {"nom": nom, "region": region},
        ).first()

        empreinte = hashlib.sha1(f"{region}|{nom}".encode("utf-8")).hexdigest()[:6].upper()
        code_etablissement = f"METFP-{_slug(region)[:10]}-{_slug(nom)[:14]}-{empreinte}"
        if ligne:
            etablissement_id = int(ligne[0])
            conn.execute(
                sa.text(
                    "UPDATE etablissementscolaire SET "
                    "code=coalesce(code, :code), type_etablissement=:type, commune=coalesce(commune, :commune), "
                    "source_officielle=:source, est_verifie=TRUE, est_actif=TRUE, date_maj=:updated "
                    "WHERE id=:id"
                ),
                {
                    "code": code_etablissement,
                    "type": type_etablissement,
                    "commune": commune,
                    "source": SOURCE_CARTOGRAPHIE,
                    "updated": maintenant,
                    "id": etablissement_id,
                },
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
                {
                    "nom": nom,
                    "code": code_etablissement,
                    "type": type_etablissement,
                    "region": region,
                    "commune": commune,
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

        # Ne pas dupliquer une offre déjà présente ; aucune offre importée n'est publiée.
        for cle_parcours in sorted(set(codes_parcours)):
            parcours_id = _id_parcours(conn, cle_parcours)
            code_offre = "FORMATION:" + _slug(cle_parcours)
            existe = conn.execute(
                sa.text(
                    "SELECT id FROM offreetablissementscolaire WHERE etablissement_id=:etablissement "
                    "AND code_offre=:code AND annee_scolaire IS NULL AND est_active=TRUE"
                ),
                {"etablissement": etablissement_id, "code": code_offre},
            ).first()
            if existe:
                continue
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


def downgrade() -> None:
    # Revenir en arrière automatiquement supprimerait des lignes potentiellement
    # retouchées par un administrateur ; les données de catalogue sont conservées.
    pass
