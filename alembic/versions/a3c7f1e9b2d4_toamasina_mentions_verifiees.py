"""toamasina : normalisation des noms de mentions + ajout de parcours/mentions verifies

Revision ID: a3c7f1e9b2d4
Revises: 30de0154f0ca
Create Date: 2026-08-20 10:00:00.000000

Perimetre : uniquement l'Universite de Toamasina (§11 du brief refonte
academique nationale : "ameliorer l'existant, pas le remplacer
aveuglement"). Les 5 autres universites restent hors scope de cette
migration (elles ont 0 filiere a ce jour, cf. f2b8e6a1c9d3) et seront
traitees separement.

Source principale : site officiel https://www.univ-toamasina.mg
(facultes/deg, facultes/lettres, facultes/medecine, facultes/sciences)
+ sous-domaine officiel https://degmia.univ-toamasina.mg, consultes le
20/08/2026.

REGLE RESPECTEE : rien n'est renomme/supprime de facon destructive pour
un etudiant deja inscrit. Les Filiere existantes ("Droit", "Economie",
"Gestion", "Medecine generale"...) restent en place avec leur id intact
(des Utilisateur.filiere_id peuvent pointer dessus). On AJOUTE les
paliers plus precis (parcours) confirmes par la source officielle, et
on renomme uniquement les Mention (qui n'ont aucune consequence sur les
comptes existants : verifie via referentiel_academique.py, qui compare
des ID, jamais des noms) vers leur intitule officiel exact.

Point tranche explicitement (conflit releve pendant la recherche) :
"Mathematiques, Informatique et Applications" est rattachee a la
faculte DEGMIA, pas a "Sciences et Technologie" -- confirmee par le
sous-domaine officiel degmia.univ-toamasina.mg qui l'enumere comme une
des "quatre filieres generales" de DEGMIA, ET par la structure deja
existante en base (la Faculte "Sciences et Technologies" seedee par ce
projet n'a jamais contenu cette filiere : elle a toujours ete rattachee
a la faculte DEGMIA). La page facultes/sciences/ du site officiel la
mentionne aussi, mais sans lister de faculte de rattachement explicite
dans le texte recupere -- l'evidence converge donc vers DEGMIA.

Non ajoute / laisse en l'etat (a verifier plus tard, pas invente) :
- Le detail des parcours de L3/M1/M2 pour "Sciences Economiques" et
  "Gestion" (les parcours differents par niveau ne rentrent pas
  proprement dans le modele Filiere actuel, qui est cense representer
  un parcours stable sur toute la scolarite d'un etudiant -- necessite
  une decision de modelisation avec Jake avant d'etre ajoute).
- Le detail complet de la Faculte "Sciences et Technologie" (seule la
  mention Mathematiques/Info a pu etre confirmee et rattachee a DEGMIA
  ; Physique/Chimie/SVT existent deja en base depuis le seed initial
  mais n'ont pas encore ete recroisees avec le site officiel).
- Le detail complet de la Faculte "Lettres et Sciences Humaines" au-
  dela de ce qui est deja en base (HDD et Philosophie mentionnees sur
  le site mais parcours non entierement recuperes).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3c7f1e9b2d4'
down_revision: Union[str, None] = '30de0154f0ca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# --- 1) Renommage de Mention vers l'intitule officiel exact (§13 :
#     normalisation, mais le nom officiel reste prioritaire -- ici on
#     va justement VERS le nom officiel, pas vers une version
#     esthetique inventee). Purement cosmetique pour les comptes
#     existants (aucune FK ne pointe sur un nom, uniquement sur l'id).
RENOMMAGE_MENTIONS = {
    "Droit": "Droit et Sciences Politiques",
    "Sciences Economiques": "Sciences Economiques",  # deja correct, gardee pour lisibilite du mapping
    "Sciences de Gestion": "Gestion",
    "Mathematiques et Informatique": "Mathematiques, Informatique et Applications",
}

# --- 2) Nouveaux parcours (paliers Filiere) confirmes par le site
#     officiel, a ajouter SOUS des mentions existantes (renommees ci-
#     dessus si besoin). (nom_mention_officiel, nom_faculte_actuelle, [nouveaux noms de filiere])
NOUVEAUX_PARCOURS = [
    ("Droit et Sciences Politiques", "Droit, Economie, Gestion, Mathematiques et Informatique (DEGMIA)",
     ["Droit Prive", "Droit Public"]),
]

# --- 3) Nouvelles mentions + filiere associee (formations entierement
#     absentes de la base aujourd'hui, confirmees par facultes/medecine/).
#     (nom_mention, nom_faculte_actuelle, nom_filiere)
NOUVELLES_MENTIONS = [
    ("Sage-Femme", "Medecine", "Sage-Femme"),
    ("Soins Infirmiers", "Medecine", "Infirmiere"),
]

# --- 4) La mention generique "Medecine" existante correspond en fait a
#     "Medecine Humaine" (une des 3 mentions officielles de la faculte,
#     confirmee par facultes/medecine/) -- simple renommage, meme
#     logique que RENOMMAGE_MENTIONS.
RENOMMAGE_MENTION_MEDECINE = ("Medecine", "Medecine Humaine")


def upgrade() -> None:
    connexion = op.get_bind()

    # --- 1) Renommages de mentions ---
    tous_renommages = dict(RENOMMAGE_MENTIONS)
    tous_renommages[RENOMMAGE_MENTION_MEDECINE[0]] = RENOMMAGE_MENTION_MEDECINE[1]
    for ancien_nom, nouveau_nom in tous_renommages.items():
        if ancien_nom == nouveau_nom:
            continue
        connexion.execute(
            sa.text("UPDATE mention SET nom = :nouveau WHERE nom = :ancien")
            .bindparams(nouveau=nouveau_nom, ancien=ancien_nom)
        )

    # --- 2) Nouveaux parcours sous des mentions existantes ---
    for nom_mention, nom_faculte, nouveaux_parcours in NOUVEAUX_PARCOURS:
        mention_id = connexion.execute(
            sa.text("SELECT id FROM mention WHERE nom = :nom").bindparams(nom=nom_mention)
        ).scalar()
        faculte_id = connexion.execute(
            sa.text("SELECT id FROM faculte WHERE nom = :nom").bindparams(nom=nom_faculte)
        ).scalar()
        if mention_id is None or faculte_id is None:
            # Ne devrait pas arriver si f2b8e6a1c9d3 et e1a4c9d2b7f5 ont
            # bien tourne avant celle-ci -- on ne plante pas silencieusement
            # une base qui n'aurait pas le seed attendu, mais on ne bloque
            # pas non plus un environnement de test minimal.
            continue
        for nom_parcours in nouveaux_parcours:
            deja_existe = connexion.execute(
                sa.text("SELECT id FROM filiere WHERE nom = :nom AND faculte_id = :fid")
                .bindparams(nom=nom_parcours, fid=faculte_id)
            ).scalar()
            if deja_existe:
                continue
            connexion.execute(
                sa.text(
                    "INSERT INTO filiere (nom, faculte_id, mention_id) "
                    "VALUES (:nom, :fid, :mid)"
                ).bindparams(nom=nom_parcours, fid=faculte_id, mid=mention_id)
            )
            nouvelle_filiere_id = connexion.execute(
                sa.text("SELECT id FROM filiere WHERE nom = :nom AND faculte_id = :fid")
                .bindparams(nom=nom_parcours, fid=faculte_id)
            ).scalar()
            universite_toamasina_id = connexion.execute(
                sa.text("SELECT id FROM universite WHERE nom = 'Universite de Toamasina'")
            ).scalar()
            connexion.execute(
                sa.text(
                    "INSERT INTO programmeuniversitaire (universite_id, filiere_id, est_active) "
                    "VALUES (:uid, :fid, TRUE)"
                ).bindparams(uid=universite_toamasina_id, fid=nouvelle_filiere_id)
            )

    # --- 3) Nouvelles mentions (Sage-Femme, Infirmiere) + filiere ---
    universite_toamasina_id = connexion.execute(
        sa.text("SELECT id FROM universite WHERE nom = 'Universite de Toamasina'")
    ).scalar()
    for nom_mention, nom_faculte, nom_filiere in NOUVELLES_MENTIONS:
        mention_id = connexion.execute(
            sa.text("SELECT id FROM mention WHERE nom = :nom").bindparams(nom=nom_mention)
        ).scalar()
        if mention_id is None:
            connexion.execute(
                sa.text("INSERT INTO mention (nom, est_active) VALUES (:nom, TRUE)")
                .bindparams(nom=nom_mention)
            )
            mention_id = connexion.execute(
                sa.text("SELECT id FROM mention WHERE nom = :nom").bindparams(nom=nom_mention)
            ).scalar()

        faculte_id = connexion.execute(
            sa.text("SELECT id FROM faculte WHERE nom = :nom").bindparams(nom=nom_faculte)
        ).scalar()
        if faculte_id is None:
            continue

        filiere_id = connexion.execute(
            sa.text("SELECT id FROM filiere WHERE nom = :nom AND faculte_id = :fid")
            .bindparams(nom=nom_filiere, fid=faculte_id)
        ).scalar()
        if filiere_id is None:
            connexion.execute(
                sa.text(
                    "INSERT INTO filiere (nom, faculte_id, mention_id) "
                    "VALUES (:nom, :fid, :mid)"
                ).bindparams(nom=nom_filiere, fid=faculte_id, mid=mention_id)
            )
            filiere_id = connexion.execute(
                sa.text("SELECT id FROM filiere WHERE nom = :nom AND faculte_id = :fid")
                .bindparams(nom=nom_filiere, fid=faculte_id)
            ).scalar()
            connexion.execute(
                sa.text(
                    "INSERT INTO programmeuniversitaire (universite_id, filiere_id, est_active) "
                    "VALUES (:uid, :fid, TRUE)"
                ).bindparams(uid=universite_toamasina_id, fid=filiere_id)
            )


def downgrade() -> None:
    connexion = op.get_bind()

    for _nom_mention, _nom_faculte, nom_filiere in NOUVELLES_MENTIONS:
        connexion.execute(sa.text("DELETE FROM programmeuniversitaire WHERE filiere_id IN (SELECT id FROM filiere WHERE nom = :nom)").bindparams(nom=nom_filiere))
        connexion.execute(sa.text("DELETE FROM filiere WHERE nom = :nom").bindparams(nom=nom_filiere))
    for nom_mention, _nom_faculte, _nom_filiere in NOUVELLES_MENTIONS:
        connexion.execute(sa.text("DELETE FROM mention WHERE nom = :nom").bindparams(nom=nom_mention))

    for _nom_mention, _nom_faculte, nouveaux_parcours in NOUVEAUX_PARCOURS:
        for nom_parcours in nouveaux_parcours:
            connexion.execute(sa.text("DELETE FROM programmeuniversitaire WHERE filiere_id IN (SELECT id FROM filiere WHERE nom = :nom)").bindparams(nom=nom_parcours))
            connexion.execute(sa.text("DELETE FROM filiere WHERE nom = :nom").bindparams(nom=nom_parcours))

    tous_renommages = dict(RENOMMAGE_MENTIONS)
    tous_renommages[RENOMMAGE_MENTION_MEDECINE[0]] = RENOMMAGE_MENTION_MEDECINE[1]
    for ancien_nom, nouveau_nom in tous_renommages.items():
        if ancien_nom == nouveau_nom:
            continue
        connexion.execute(
            sa.text("UPDATE mention SET nom = :ancien WHERE nom = :nouveau")
            .bindparams(ancien=ancien_nom, nouveau=nouveau_nom)
        )
