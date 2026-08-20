"""antananarivo : mentions et filieres verifiees pour les 10 etablissements

Revision ID: e5b9c3f7a2d8
Revises: d4a8f2c6b9e1
Create Date: 2026-08-20 20:00:00.000000

Recherche documentaire completee le 20/08/2026 pour l'ensemble des 10
etablissements de l'Universite d'Antananarivo. Sources principales
(officielles en priorite) :
- Faculte de Droit et des Sciences Politiques : newsmada.com (dates de
  concours par filiere), tanikomadagascar.com (creation de la faculte)
- Faculte EGS : newsmada.com, site officiel FOAD Gestion
  (foadgestion-degs.org)
- FLSH : univ-antananarivo.mg (cache), moov.mg (portes ouvertes),
  iarivo-univ.info -- NOTE : le sous-domaine officiel
  flsh.univ-antananarivo.mg est actuellement pirate/defigure (contenu
  de hack), non utilisable comme source directe en ce moment
- Faculte de Medecine : facmedtananarive.org (site officiel de la
  faculte, page Mentions + fiches de preinscription 2023)
- Faculte des Sciences : univ-antananarivo.mg/Faculte-des-Sciences
  (site officiel, fiches par mention, 2022)
- ENS : univ-antananarivo.mg (site officiel), ens-foad-univ-tana.mg
  (sous-domaine officiel FOAD)
- ESPA : Wikipedia (fr) + digigasy.com (article detaille sur les 50 ans
  de l'ESPA) + polytechnique.mg (site communautaire de l'ecole,
  confirme "16 mentions")
- ESSA : univ-antananarivo.mg/Ecole-Superieure-des-Sciences-Agronomiques
  (site officiel, page Presentation-generale-139)
- IES Soavinandriana (IESSI) : Wikipedia (fr), blogderasamy.com
  (temoignage de la 1ere ceremonie de sortie de promotion)

IES Antsirabe (IES-AV) : etablissement confirme, mais mentions/parcours
NON trouves avec une confiance suffisante (site iesav.mg tres pauvre en
contenu indexe) -> AUCUNE Filiere ajoutee pour cet etablissement dans
cette migration, signale pour recherche ulterieure.

Listes volontairement incompletes, signalees ci-dessous plutot que
completees par extrapolation (regle §2 du brief : ne rien inventer) :
- ESPA : seulement 11 des 16 mentions officielles ont pu etre nommees
  avec certitude (les sources listant "16 mentions" ne les enumerent
  pas toutes explicitement)
- IES Soavinandriana : seulement 7 des 10 parcours officiels ont pu
  etre nommes (source Wikipedia tronquee)
- Faculte des Sciences : la liste de mentions a evolue depuis une
  presentation officielle de 2015 (5 mentions) vers une organisation
  plus fine documentee en 2022 (8 mentions identifiees) -- la liste
  2022, plus recente, est utilisee ici, mais n'est pas garantie
  exhaustive (page source tronquee par "(...)")
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5b9c3f7a2d8'
down_revision: Union[str, None] = 'd4a8f2c6b9e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOM_UNIVERSITE = "Universite d'Antananarivo"

# (nom_faculte_en_base, [ (nom_mention, [parcours...] ou [] si pas de
#  sous-decoupage confirme), ... ])
DONNEES = [
    ("Faculte de Droit et des Sciences Politiques", [
        ("Droit", []),
        ("Sciences Politiques", []),
    ]),
    ("Faculte d'Economie, de Gestion et de Sociologie (EGS)", [
        ("Economie", []),
        ("Sociologie", []),
        ("Gestion", []),
    ]),
    ("Faculte des Lettres et Sciences Humaines", [
        ("Etudes Malgaches", []),
        ("Etudes Francaises", []),
        ("Etudes Anglophones", []),
        ("Etudes Germaniques", []),
        ("Langues Etrangeres", ["Etudes Hispaniques", "Etudes Russes", "Langue et Culture Chinoise"]),
        ("Philosophie", []),
        ("Histoire", []),
        ("Geographie", []),
        ("Anthropologie", []),
        ("Psychologie Sociale et Interculturelle (PSI)", []),
        ("Sciences du Tourisme", []),
        ("Sciences de la Communication", []),
    ]),
    ("Faculte de Medecine", [
        ("Medecine Humaine", []),
        ("Pharmacie", []),
        ("Medecine Veterinaire", []),
        ("Sciences Paramedicales", [
            "Anesthesie", "Electroradiologie", "Ergotherapie", "Maieutique",
            "Masso-Kinesitherapie", "Sciences Infirmieres",
            "Techniques d'Appareillage Orthopedique", "Techniques de Laboratoire",
        ]),
    ]),
    ("Faculte des Sciences", [
        ("Biologie", []),
        ("Chimie", []),
        ("Physique", []),
        ("Mathematiques et Informatique", []),
        ("Informatique et Technologie", []),
        ("Anthropobiologie et Developpement Durable (MADD)", []),
        ("Biochimie Fondamentale et Appliquee (MBFA)", []),
        ("Bassins Sedimentaires, Evolution, Conservation", []),
    ]),
    ("Ecole Normale Superieure (ENS)", [
        ("Administration de l'Education (ADMED)", []),
        ("Enseignement, Apprentissage et Didactique de l'Histoire, de la Geographie et de l'Education a la Citoyennete (EAD-HGEC)", []),
        ("Enseignement, Apprentissage et Didactique des Langues et de la Philosophie (EAD-LP)", []),
        ("Enseignement, Apprentissage et Didactique des Sciences Experimentales et des Mathematiques (EAD-SEM)", []),
        ("Enseignement, Apprentissage et Didactique des Activites Physiques, Sportives et Artistiques (EAD-APSA)", []),
    ]),
    ("Ecole Superieure Polytechnique d'Antananarivo (ESPA)", [
        ("Genie Civil", ["Batiment et Travaux Publics", "Hydraulique", "Urbanisme-Architecture-Genie Civil"]),
        ("Genie des Sciences de la Terre", ["Geologie", "Mines et Petrole"]),
        ("Genie des Sciences et Technologies Industrielles", [
            "Telecommunication", "Genie Electrique", "Genie Mecanique et Industriel",
            "Sciences et Ingenierie des Materiaux",
        ]),
        ("Genie des Procedes Industriels", ["Genie Chimique et Procedes", "Industries Agroalimentaires"]),
    ]),
    ("Ecole Superieure des Sciences Agronomiques (ESSA)", [
        ("Sciences Agronomiques et Environnementales", [
            "Agriculture Tropicale et Developpement Durable", "Agro-Management",
            "Foresterie et Environnement", "Industries Agricoles et Alimentaires",
            "Sciences Animales",
        ]),
    ]),
    ("Institut d'Enseignement Superieur de Soavinandriana (Itasy)", [
        ("Licence Professionnalisante IESSI", [
            "Batiment et Travaux Publics", "Transformation Agro-Alimentaire",
            "Eau et Environnement", "Mines", "Gestion et Valorisation des Ressources Naturelles",
            "Energies Renouvelables", "Agroecologie",
        ]),
    ]),
]


def _obtenir_ou_creer_mention(connexion, nom_mention: str) -> int:
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
    return mention_id


def _obtenir_ou_creer_filiere(connexion, nom_filiere: str, faculte_id: int, mention_id: int) -> int:
    filiere_id = connexion.execute(
        sa.text("SELECT id FROM filiere WHERE nom = :nom AND faculte_id = :fid")
        .bindparams(nom=nom_filiere, fid=faculte_id)
    ).scalar()
    if filiere_id is None:
        connexion.execute(
            sa.text("INSERT INTO filiere (nom, faculte_id, mention_id) VALUES (:nom, :fid, :mid)")
            .bindparams(nom=nom_filiere, fid=faculte_id, mid=mention_id)
        )
        filiere_id = connexion.execute(
            sa.text("SELECT id FROM filiere WHERE nom = :nom AND faculte_id = :fid")
            .bindparams(nom=nom_filiere, fid=faculte_id)
        ).scalar()
    return filiere_id


def _lier_programme(connexion, universite_id: int, filiere_id: int) -> None:
    deja = connexion.execute(
        sa.text("SELECT id FROM programmeuniversitaire WHERE universite_id = :uid AND filiere_id = :fid")
        .bindparams(uid=universite_id, fid=filiere_id)
    ).scalar()
    if deja:
        return
    connexion.execute(
        sa.text("INSERT INTO programmeuniversitaire (universite_id, filiere_id, est_active) VALUES (:uid, :fid, TRUE)")
        .bindparams(uid=universite_id, fid=filiere_id)
    )


def upgrade() -> None:
    connexion = op.get_bind()

    universite_id = connexion.execute(
        sa.text("SELECT id FROM universite WHERE nom = :nom").bindparams(nom=NOM_UNIVERSITE)
    ).scalar()
    if universite_id is None:
        return

    for nom_faculte, mentions in DONNEES:
        faculte_id = connexion.execute(
            sa.text("SELECT id FROM faculte WHERE nom = :nom AND universite_id = :uid")
            .bindparams(nom=nom_faculte, uid=universite_id)
        ).scalar()
        if faculte_id is None:
            continue

        for nom_mention, parcours in mentions:
            mention_id = _obtenir_ou_creer_mention(connexion, nom_mention)

            if parcours:
                for nom_parcours in parcours:
                    filiere_id = _obtenir_ou_creer_filiere(connexion, nom_parcours, faculte_id, mention_id)
                    _lier_programme(connexion, universite_id, filiere_id)
            else:
                # Pas de sous-decoupage en parcours confirme : la
                # Filiere porte directement le nom de la Mention.
                filiere_id = _obtenir_ou_creer_filiere(connexion, nom_mention, faculte_id, mention_id)
                _lier_programme(connexion, universite_id, filiere_id)


def downgrade() -> None:
    connexion = op.get_bind()

    universite_id = connexion.execute(
        sa.text("SELECT id FROM universite WHERE nom = :nom").bindparams(nom=NOM_UNIVERSITE)
    ).scalar()
    if universite_id is None:
        return

    for nom_faculte, mentions in DONNEES:
        faculte_id = connexion.execute(
            sa.text("SELECT id FROM faculte WHERE nom = :nom AND universite_id = :uid")
            .bindparams(nom=nom_faculte, uid=universite_id)
        ).scalar()
        if faculte_id is None:
            continue

        for nom_mention, parcours in mentions:
            noms_filieres = parcours if parcours else [nom_mention]
            for nom_filiere in noms_filieres:
                filiere_id = connexion.execute(
                    sa.text("SELECT id FROM filiere WHERE nom = :nom AND faculte_id = :fid")
                    .bindparams(nom=nom_filiere, fid=faculte_id)
                ).scalar()
                if filiere_id is not None:
                    connexion.execute(
                        sa.text("DELETE FROM programmeuniversitaire WHERE filiere_id = :fid AND universite_id = :uid")
                        .bindparams(fid=filiere_id, uid=universite_id)
                    )
                    connexion.execute(sa.text("DELETE FROM filiere WHERE id = :fid").bindparams(fid=filiere_id))

            # Mention potentiellement partagee avec une autre universite
            # (ex: "Philosophie" existe aussi pour Toamasina) -> ne
            # supprimer que si plus aucune Filiere n'y fait reference.
            encore_utilisee = connexion.execute(
                sa.text("SELECT COUNT(*) FROM filiere WHERE mention_id = (SELECT id FROM mention WHERE nom = :nom)")
                .bindparams(nom=nom_mention)
            ).scalar()
            if not encore_utilisee:
                connexion.execute(sa.text("DELETE FROM mention WHERE nom = :nom").bindparams(nom=nom_mention))
