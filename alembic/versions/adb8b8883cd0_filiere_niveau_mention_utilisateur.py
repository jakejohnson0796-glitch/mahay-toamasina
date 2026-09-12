"""filiere.niveau + utilisateur.mention_id + import referentiel Toamasina par niveau

Revision ID: adb8b8883cd0
Revises: 526f828e83d2
Create Date: 2026-09-10 18:00:00.000000

Suite au rapport d'analyse du 10/09/2026 (fichier fourni :
Base_Donnees_Universite_Toamasina_Mahay.xlsx), qui repond a la question
laissee ouverte dans a3c7f1e9b2d4 ("necessite une decision de
modelisation avec Jake avant d'etre ajoute").

DEUX CHANGEMENTS DE SCHEMA (additifs, aucune colonne/table supprimee) :

1) Filiere.niveau (nullable) : une ligne Filiere represente desormais un
   triplet (mention, niveau, nom de parcours) et non plus un nom seul
   sense couvrir toute la scolarite. Les lignes existantes gardent
   niveau=NULL (heritees, non-datees) -- jamais invalidees, juste moins
   precises qu'une nouvelle ligne.

2) Utilisateur.mention_id (nullable, FK mention.id) : jusqu'ici "la
   filiere EST la mention" (§6 du brief) -- mais un etudiant en tronc
   commun (avant specialisation, ex: tout L1) n'a justement AUCUNE
   filiere, et se retrouvait donc sans mention du tout, marque en
   permanence "profil academique incomplet" (voir
   referentiel_academique.py, corrige dans une migration/patch separe).
   Ce champ se renseigne des le tronc commun, independamment de
   filiere_id.

IMPORT DE DONNEES (Faculte DEG + FST + ENS uniquement -- Faculte des
Lettres et Sciences Humaines volontairement exclue : toutes ses lignes
du fichier sont au statut "A completer / verifier", le fichier lui-meme
demande une confirmation officielle avant import) :

- Lignes "Tronc commun" : jamais materialisees en Filiere (voir §3 du
  rapport -- le tronc commun est l'ABSENCE d'une ligne Filiere pour ce
  (mention, niveau), pas une valeur/ligne a stocker).
- "Droit Prive", "Droit Public" (deja en base, sans niveau, crees par
  a3c7f1e9b2d4) et "Mathematiques et Informatique" (deja en base,
  faculte corrigee par b7e2d4a8c1f6) : reutilises pour leur niveau L3
  (premiere specialisation de ces parcours) plutot que dupliques ; les
  niveaux suivants (M1/M2 pour Droit) sont des nouvelles lignes.
- DEUX DIVERGENCES reperees avec des donnees deja verifiees
  precedemment, PAS resolues ici par devinette (§44 du brief) :

  a) Le fichier groupe "Physique" et "Chimie" sous UNE mention
     "Physique-Chimie". Or Physique et Chimie existent deja en base
     comme DEUX mentions distinctes depuis le seed initial (confirme
     par le commentaire de a3c7f1e9b2d4 : "Physique/Chimie/SVT existent
     deja en base depuis le seed initial"). Les parcours de L2/L3
     ("Physique", "Chimie") sont sans ambiguite rattaches chacun a sa
     mention existante. Les 5 parcours de M1/M2 (Energetique, Physique
     nucleaire appliquee et Environnement, Sciences du Climat et des
     Materiaux, Chimie Biologie, Chimie des Procedes et Chimie Marine)
     NE precisent PAS explicitement laquelle des deux mentions ils
     rejoignent -- crees avec mention_id=NULL, pour revue humaine sur
     /admin/referentiel (ecran deja prevu exactement pour ce cas, voir
     nb_filieres_sans_mention).

  b) Le fichier decrit 11 mentions ENS "Enseignement-Apprentissage et
     didactique de/en X". Or l'ENS a deja une mention verifiee "Sciences
     de l'Education et Administration Scolaire (SEAS)" (creee par
     c9f1a6e3d8b2, source : meme flyer ENS_Flyers.pdf). Les deux
     descriptions de l'ENS ne sont pas fusionnees ici (noms et parcours
     entierement differents, aucune correspondance evidente) : les 11
     nouvelles mentions sont ajoutees TELLES QUELLES, en plus de SEAS,
     qui n'est pas touchee. A clarifier par un admin ayant acces au
     flyer complet.

Idempotente : chaque insertion passe par un get-or-create (par nom
normalise), peut etre rejouee sans creer de doublon.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = 'adb8b8883cd0'
down_revision: Union[str, None] = '526f828e83d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# =====================================================================
# Donnees curatees depuis Base_Donnees_Universite_Toamasina_Mahay.xlsx
# (lignes "Verifie"/"Confirme" uniquement). Format :
#   (nom_mention, [(niveau, [noms_de_parcours])])
# =====================================================================

NOM_FACULTE_DEGMIA = "Droit, Economie, Gestion, Mathematiques et Informatique (DEGMIA)"
NOM_FACULTE_SCIENCES = "Sciences et Technologies"
NOM_FACULTE_ENS = "Ecole Normale Superieure (ENS)"

# --- Mentions DEGMIA existantes : (mention, faculte, [(niveau, [parcours])]) ---
PARCOURS_MENTIONS_EXISTANTES = [
    ("Droit et Sciences Politiques", NOM_FACULTE_DEGMIA, [
        ("L3", ["Droit Prive", "Droit Public"]),
        ("M1", ["Droit Prive", "Droit Public"]),
        ("M2", ["Droit Prive", "Droit Public"]),
    ]),
    ("Sciences Economiques", NOM_FACULTE_DEGMIA, [
        ("L3", ["Economie et gestion d'entreprise", "Analyse economique", "Economie mathematique"]),
        ("M1", ["Economie mathematique", "Politique publique", "Economie du developpement"]),
        ("M2", ["Economie de la sante et des sciences sociales", "Economie du developpement", "Economie publique"]),
    ]),
    ("Gestion", NOM_FACULTE_DEGMIA, [
        ("L3", ["Gestion des Ressources Humaines", "Entreprises agro-industrielles et Commerce International", "Finances et comptabilite"]),
        ("M1", ["Banques et Finances", "Commerce International", "CCA - Comptabilite, Controle, Audit"]),
        # "Commerce International" n'a pas de ligne M2 explicite dans le
        # fichier source (seules les colonnes Debut/Fin le suggerent) --
        # non ajoute ici, voir §2.3 du rapport (ne jamais deviner au-dela
        # de ce qui est ecrit noir sur blanc).
        ("M2", ["Banques et Finances", "CCA - Comptabilite, Controle, Audit"]),
    ]),
    ("Mathematiques, Informatique et Applications", NOM_FACULTE_SCIENCES, [
        ("L3", ["Informatique Academique", "Mathematiques et Informatique"]),
        ("M1", ["Genie Informatique", "Image et Interaction", "Ingenierie mathematique"]),
        ("M2", ["Genie Informatique", "Image et Interaction", "Ingenierie mathematique"]),
    ]),
    # Physique et Chimie : mentions deja existantes (seed initial), PAS
    # une mention combinee "Physique-Chimie" (voir divergence (a) plus haut).
    ("Physique", NOM_FACULTE_SCIENCES, [
        ("L2", ["Physique"]),
        ("L3", ["Physique"]),
    ]),
    ("Chimie", NOM_FACULTE_SCIENCES, [
        ("L2", ["Chimie"]),
        ("L3", ["Chimie"]),
    ]),
]

# --- Parcours M1/M2 "Physique-Chimie" du fichier SANS mention assignee
#     (divergence (a) ci-dessus) : crees avec mention_id=NULL pour revue
#     sur /admin/referentiel. ---
PARCOURS_SANS_MENTION_PHYSIQUE_CHIMIE = {
    NOM_FACULTE_SCIENCES: [
        ("M1", ["Energetique", "Physique nucleaire appliquee et Environnement", "Sciences du Climat et des Materiaux", "Chimie Biologie", "Chimie des Procedes et Chimie Marine"]),
        ("M2", ["Energetique", "Physique nucleaire appliquee et Environnement", "Sciences du Climat et des Materiaux", "Chimie Biologie", "Chimie des Procedes et Chimie Marine"]),
    ],
}

# --- Nouvelles mentions ENS (divergence (b) ci-dessus : coexistent avec
#     SEAS, ne la remplacent pas). Domaine "Sciences de l'education et
#     didactique" (meme domaine que SEAS). ---
NOM_DOMAINE_ENS = "Sciences de l'education et didactique"

NOUVELLES_MENTIONS_ENS_AVEC_PARCOURS = [
    ("Enseignement-Apprentissage et didactique de la Philosophie", [
        ("M1", ["Histoire de la philosophie, epistemologie et enseignement", "Formation d'enseignant de la Philosophie", "Culture et societe"]),
        ("M2", ["Histoire de la philosophie, epistemologie et enseignement", "Formation d'enseignant de la Philosophie", "Culture et societe"]),
    ]),
    ("Enseignement-Apprentissage et didactique d'Histoire-Geographie", [
        ("M1", ["Enseignement - Apprentissage et didactique d'Histoire-Geographie", "Formation d'enseignant d'education a la citoyennete"]),
        ("M2", ["Enseignement - Apprentissage et didactique d'Histoire-Geographie", "Formation d'enseignant d'education a la citoyennete"]),
    ]),
    ("Enseignement-Apprentissage et didactique en Ingenierie Mathematiques-Informatique", [
        ("M1", ["Informatique", "Mathematiques fondamentales", "Mathematiques-statistique-informatique"]),
        ("M2", ["Informatique", "Mathematiques fondamentales", "Mathematiques-statistique-informatique"]),
    ]),
    ("Enseignement-Apprentissage et didactique de Physique-Chimie", [
        ("M1", ["Enseignement - Apprentissage et didactique de Physique Chimie"]),
        ("M2", ["Enseignement - Apprentissage et didactique de Physique Chimie"]),
    ]),
]

# --- Mentions ENS supplementaires, tronc-commun UNIQUEMENT dans les
#     donnees verifiees a ce jour (aucun parcours de specialisation
#     confirme pour elles) : mention creee quand meme, pour que les
#     etudiants de ces filieres en tronc commun aient un mention_id --
#     mais aucune Filiere associee tant qu'aucune specialisation n'est
#     verifiee. ---
NOUVELLES_MENTIONS_ENS_TRONC_COMMUN_SEUL = [
    "Enseignement-Apprentissage et didactique en Organisation Sociale et Economique",
    "Enseignement-Apprentissage et didactique en Sciences Economiques et Sociales",
    "Enseignement-Apprentissage et didactique de la Langue Malagasy",
    "Enseignement-Apprentissage et didactique de la Langue Francaise",
    "Enseignement-Apprentissage et didactique de la Langue Anglaise",
    "Enseignement-Apprentissage et didactique en Sciences Naturelles",
    "Enseignement-Apprentissage et didactique en Sciences de l'Education",
]


def _normaliser(texte: str) -> str:
    import re
    import unicodedata
    if not texte:
        return ""
    texte = texte.strip().replace("\u2019", "'")
    texte = unicodedata.normalize("NFKD", texte)
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    texte = re.sub(r"\s+", " ", texte)
    return texte.lower()


def upgrade() -> None:
    # --- 1) Schema (additif) ---
    op.add_column('filiere', sa.Column('niveau', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('utilisateur', sa.Column('mention_id', sa.Integer(), nullable=True))
    with op.batch_alter_table('utilisateur') as batch_op:
        batch_op.create_foreign_key('fk_utilisateur_mention', 'mention', ['mention_id'], ['id'])

    connexion = op.get_bind()

    universite_toamasina_id = connexion.execute(
        sa.text("SELECT id FROM universite WHERE nom = 'Universite de Toamasina'")
    ).scalar()
    if universite_toamasina_id is None:
        # Ne devrait pas arriver (seedee depuis le tout debut) -- garde-fou
        # pour ne jamais planter sur un environnement de test minimal.
        return

    def _obtenir_faculte_id(nom_faculte: str) -> int | None:
        return connexion.execute(
            sa.text("SELECT id FROM faculte WHERE nom = :nom AND universite_id = :uid")
            .bindparams(nom=nom_faculte, uid=universite_toamasina_id)
        ).scalar()

    def _obtenir_mention_id(nom_mention: str) -> int | None:
        toutes = connexion.execute(sa.text("SELECT id, nom FROM mention")).fetchall()
        cible = _normaliser(nom_mention)
        for mid, nom in toutes:
            if _normaliser(nom) == cible:
                return mid
        return None

    def _creer_mention(nom_mention: str, domaine_id: int | None = None) -> int:
        connexion.execute(
            sa.text("INSERT INTO mention (nom, domaine_id, est_active) VALUES (:nom, :did, TRUE)")
            .bindparams(nom=nom_mention, did=domaine_id)
        )
        return _obtenir_mention_id(nom_mention)

    def _obtenir_ou_creer_filiere(nom_parcours: str, faculte_id: int, mention_id: int | None, niveau: str) -> int:
        """Reutilise en priorite une ligne existante SANS niveau (meme
        nom normalise, meme faculte) en lui affectant ce niveau --
        c'est le cas "Droit Prive"/"Droit Public"/"Mathematiques et
        Informatique" deja en base. Sinon, reutilise une ligne qui a
        deja EXACTEMENT ce niveau (relance idempotente). Sinon, cree."""
        cible = _normaliser(nom_parcours)
        lignes = connexion.execute(
            sa.text("SELECT id, nom, niveau FROM filiere WHERE faculte_id = :fid")
            .bindparams(fid=faculte_id)
        ).fetchall()

        for fid, nom, niveau_existant in lignes:
            if _normaliser(nom) == cible and niveau_existant == niveau:
                return fid  # deja fait (relance idempotente)

        for fid, nom, niveau_existant in lignes:
            if _normaliser(nom) == cible and niveau_existant is None:
                connexion.execute(
                    sa.text("UPDATE filiere SET niveau = :niveau, mention_id = COALESCE(mention_id, :mid) WHERE id = :fid")
                    .bindparams(niveau=niveau, mid=mention_id, fid=fid)
                )
                return fid

        connexion.execute(
            sa.text("INSERT INTO filiere (nom, faculte_id, mention_id, niveau) VALUES (:nom, :fid, :mid, :niveau)")
            .bindparams(nom=nom_parcours, fid=faculte_id, mid=mention_id, niveau=niveau)
        )
        return connexion.execute(
            sa.text("SELECT id FROM filiere WHERE faculte_id = :fid AND nom = :nom AND niveau = :niveau")
            .bindparams(fid=faculte_id, nom=nom_parcours, niveau=niveau)
        ).scalar()

    def _lier_programme(filiere_id: int) -> None:
        deja = connexion.execute(
            sa.text("SELECT id FROM programmeuniversitaire WHERE universite_id = :uid AND filiere_id = :fid")
            .bindparams(uid=universite_toamasina_id, fid=filiere_id)
        ).scalar()
        if not deja:
            connexion.execute(
                sa.text("INSERT INTO programmeuniversitaire (universite_id, filiere_id, est_active) VALUES (:uid, :fid, TRUE)")
                .bindparams(uid=universite_toamasina_id, fid=filiere_id)
            )

    # --- 2) Mentions existantes : parcours par niveau ---
    for nom_mention, nom_faculte, par_niveau in PARCOURS_MENTIONS_EXISTANTES:
        mention_id = _obtenir_mention_id(nom_mention)
        faculte_id = _obtenir_faculte_id(nom_faculte)
        if mention_id is None or faculte_id is None:
            continue  # ne devrait pas arriver (verifie dans le rapport) ; jamais deviner un id
        for niveau, noms_parcours in par_niveau:
            for nom_parcours in noms_parcours:
                fid = _obtenir_ou_creer_filiere(nom_parcours, faculte_id, mention_id, niveau)
                _lier_programme(fid)

    # --- 3) Parcours Physique-Chimie M1/M2 sans mention (divergence a) ---
    for nom_faculte, par_niveau in PARCOURS_SANS_MENTION_PHYSIQUE_CHIMIE.items():
        faculte_id = _obtenir_faculte_id(nom_faculte)
        if faculte_id is None:
            continue
        for niveau, noms_parcours in par_niveau:
            for nom_parcours in noms_parcours:
                fid = _obtenir_ou_creer_filiere(nom_parcours, faculte_id, None, niveau)
                _lier_programme(fid)

    # --- 4) Nouvelles mentions ENS (divergence b) ---
    domaine_ens_id = connexion.execute(
        sa.text("SELECT id FROM domaine WHERE nom = :nom").bindparams(nom=NOM_DOMAINE_ENS)
    ).scalar()
    faculte_ens_id = _obtenir_faculte_id(NOM_FACULTE_ENS)

    for nom_mention, par_niveau in NOUVELLES_MENTIONS_ENS_AVEC_PARCOURS:
        mention_id = _obtenir_mention_id(nom_mention) or _creer_mention(nom_mention, domaine_ens_id)
        if faculte_ens_id is None:
            continue
        for niveau, noms_parcours in par_niveau:
            for nom_parcours in noms_parcours:
                fid = _obtenir_ou_creer_filiere(nom_parcours, faculte_ens_id, mention_id, niveau)
                _lier_programme(fid)

    for nom_mention in NOUVELLES_MENTIONS_ENS_TRONC_COMMUN_SEUL:
        _obtenir_mention_id(nom_mention) or _creer_mention(nom_mention, domaine_ens_id)

    # --- 5) Backfill Utilisateur.mention_id depuis filiere_id existant
    #     (deduction mecanique, deja ce que le code fait a la volee
    #     aujourd'hui -- on ne fait que le stocker en plus). ---
    connexion.execute(sa.text(
        "UPDATE utilisateur SET mention_id = ("
        "  SELECT f.mention_id FROM filiere f WHERE f.id = utilisateur.filiere_id"
        ") WHERE utilisateur.filiere_id IS NOT NULL AND utilisateur.mention_id IS NULL"
    ))


def downgrade() -> None:
    with op.batch_alter_table('utilisateur') as batch_op:
        batch_op.drop_constraint('fk_utilisateur_mention', type_='foreignkey')
        batch_op.drop_column('mention_id')
    op.drop_column('filiere', 'niveau')
