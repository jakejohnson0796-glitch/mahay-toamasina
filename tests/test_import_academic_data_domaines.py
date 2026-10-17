import json
import tempfile
from pathlib import Path

from sqlalchemy import event
from sqlmodel import SQLModel, Session, create_engine, select

from app.models import Domaine, Mention
from scripts.import_academic_data import (
    Rapport,
    _canonicaliser_domaines_existants,
    canoniser_domaine,
    lire_lignes_source,
)


DOMAINE_CANONIQUE = "Sciences de l’éducation"
DOMAINE_ALIAS = "Sciences de l'éducation et didactique"


def nouvel_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def activer_cles_etrangeres(connexion, _record):
        connexion.execute("PRAGMA foreign_keys=ON")

    SQLModel.metadata.create_all(engine)
    return engine


def test_canonise_alias_domaine_ens():
    assert canoniser_domaine(DOMAINE_ALIAS) == DOMAINE_CANONIQUE
    assert canoniser_domaine(DOMAINE_CANONIQUE) == DOMAINE_CANONIQUE


def test_fusionne_alias_et_reaffecte_les_mentions_sans_perdre_les_liens():
    engine = nouvel_engine()
    try:
        with Session(engine) as session:
            domaine_canonique = Domaine(nom=DOMAINE_CANONIQUE)
            domaine_alias = Domaine(nom=DOMAINE_ALIAS)
            session.add(domaine_canonique)
            session.add(domaine_alias)
            session.commit()
            session.refresh(domaine_canonique)
            session.refresh(domaine_alias)

            mention_alias = Mention(nom="Mention ENS reliée à l’alias", domaine_id=domaine_alias.id)
            mention_canonique = Mention(nom="Mention ENS déjà canonique", domaine_id=domaine_canonique.id)
            session.add(mention_alias)
            session.add(mention_canonique)
            session.commit()
            mention_alias_id = mention_alias.id
            cible_id = domaine_canonique.id

            rapport = Rapport()
            _canonicaliser_domaines_existants(session, dry_run=False, rapport=rapport)

            domaines = session.exec(select(Domaine)).all()
            liens = session.exec(select(Mention)).all()
            assert len(domaines) == 1
            assert domaines[0].id == cible_id
            assert {mention.domaine_id for mention in liens} == {cible_id}
            assert any(mention.id == mention_alias_id for mention in liens)
            assert rapport.domaines_canonicalises == [(DOMAINE_ALIAS, DOMAINE_CANONIQUE)]
    finally:
        engine.dispose()


def test_renomme_alias_si_le_domaine_cible_n_existe_pas():
    engine = nouvel_engine()
    try:
        with Session(engine) as session:
            domaine = Domaine(nom=DOMAINE_ALIAS)
            session.add(domaine)
            session.commit()
            session.refresh(domaine)
            identifiant = domaine.id

            mention = Mention(nom="Mention à conserver", domaine_id=domaine.id)
            session.add(mention)
            session.commit()

            rapport = Rapport()
            _canonicaliser_domaines_existants(session, dry_run=False, rapport=rapport)

            domaines = session.exec(select(Domaine)).all()
            mention_chargee = session.get(Mention, mention.id)
            assert len(domaines) == 1
            assert domaines[0].id == identifiant
            assert domaines[0].nom == DOMAINE_CANONIQUE
            assert mention_chargee is not None
            assert mention_chargee.domaine_id == identifiant
            assert rapport.domaines_canonicalises == [(DOMAINE_ALIAS, DOMAINE_CANONIQUE)]
    finally:
        engine.dispose()


def test_lecture_json_canonise_le_domaine_avant_agrégation_des_mentions():
    payload = {
        "formations": [
            {
                "universite": "Université de Toamasina",
                "ville": "Toamasina",
                "composante": "École Normale Supérieure",
                "domaine": DOMAINE_ALIAS,
                "mention": "Enseignement-Apprentissage et didactique de la Langue Malagasy",
                "niveau": "L1",
                "type": "Tronc commun",
                "parcours": "Tronc commun",
                "statut": "Vérifié",
            },
            {
                "universite": "Université de Toamasina",
                "ville": "Toamasina",
                "composante": "École Normale Supérieure",
                "domaine": DOMAINE_CANONIQUE,
                "mention": "Enseignement-Apprentissage et didactique de la Langue Malagasy",
                "niveau": "M1",
                "type": "Spécialisation",
                "parcours": "Littérature et linguistique Malagasy",
                "statut": "Vérifié",
            },
        ]
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as fichier:
        json.dump(payload, fichier, ensure_ascii=False)
        chemin = Path(fichier.name)

    try:
        lignes = lire_lignes_source(str(chemin))
    finally:
        chemin.unlink(missing_ok=True)

    assert {ligne["domaine"] for ligne in lignes} == {DOMAINE_CANONIQUE}



def test_dry_run_ne_persiste_ni_fusion_ni_reaffectation():
    engine = nouvel_engine()
    try:
        with Session(engine) as session:
            domaine_canonique = Domaine(nom=DOMAINE_CANONIQUE)
            domaine_alias = Domaine(nom=DOMAINE_ALIAS)
            session.add(domaine_canonique)
            session.add(domaine_alias)
            session.commit()
            session.refresh(domaine_canonique)
            session.refresh(domaine_alias)
            id_canonique = domaine_canonique.id
            id_alias = domaine_alias.id

            mention = Mention(nom="Mention de test dry-run", domaine_id=id_alias)
            session.add(mention)
            session.commit()
            id_mention = mention.id

            rapport = Rapport()
            _canonicaliser_domaines_existants(session, dry_run=True, rapport=rapport)
            session.rollback()

        with Session(engine) as verification:
            domaines = verification.exec(select(Domaine).order_by(Domaine.id)).all()
            mention_verifiee = verification.get(Mention, id_mention)
            assert len(domaines) == 2
            assert {domaine.id for domaine in domaines} == {id_canonique, id_alias}
            assert mention_verifiee is not None
            assert mention_verifiee.domaine_id == id_alias
            assert rapport.domaines_canonicalises == [(DOMAINE_ALIAS, DOMAINE_CANONIQUE)]
    finally:
        engine.dispose()
