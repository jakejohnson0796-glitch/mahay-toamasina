from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine, select

from app.models import (
    AffectationSousSalle,
    ConsentementTranscription,
    Cours,
    GroupeSousSalle,
    ReponseSondageSeance,
    RoleUtilisateur,
    Seance,
    SondageSeance,
    TranscriptionSeance,
    Utilisateur,
)

ROOT = Path(__file__).resolve().parents[1]


def creer_utilisateur(nom, telephone, role):
    return Utilisateur(
        nom=nom,
        telephone=telephone,
        mot_de_passe_hash="hash-test",
        role=role,
    )


def creer_base():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


def creer_seance(session):
    professeur = creer_utilisateur("Professeur", "+261340000901", RoleUtilisateur.PROFESSEUR)
    eleve_a = creer_utilisateur("Élève A", "+261340000902", RoleUtilisateur.ETUDIANT)
    eleve_b = creer_utilisateur("Élève B", "+261340000903", RoleUtilisateur.ETUDIANT)
    session.add_all([professeur, eleve_a, eleve_b])
    session.commit()
    session.refresh(professeur)
    session.refresh(eleve_a)
    session.refresh(eleve_b)
    cours = Cours(
        nom="Mathématiques",
        matiere="Mathématiques",
        niveau="L1",
        professeur_id=professeur.id,
    )
    session.add(cours)
    session.commit()
    session.refresh(cours)
    seance = Seance(
        cours_id=cours.id,
        titre="Fonctions",
        nom_salle_livekit="interactions-test",
    )
    session.add(seance)
    session.commit()
    session.refresh(seance)
    return professeur, eleve_a, eleve_b, cours, seance


def test_modeles_interactions_creent_le_schema_sqlite():
    engine = creer_base()
    tables = set(SQLModel.metadata.tables)
    attendues = {
        "sondageseance",
        "reponsesondageseance",
        "groupesoussalle",
        "affectationsoussalle",
        "documentpartageseance",
        "consentementtranscription",
        "transcriptionseance",
    }
    assert attendues.issubset(tables)
    engine.dispose()


def test_un_eleve_ne_peut_pas_repondre_deux_fois_au_meme_sondage():
    engine = creer_base()
    with Session(engine) as session:
        _prof, eleve_a, _eleve_b, cours, seance = creer_seance(session)
        sondage = SondageSeance(
            seance_id=seance.id,
            cours_id=cours.id,
            createur_id=1,
            question="Combien font 2 + 2 ?",
            options_json='["3", "4"]',
            type_sondage="quiz",
            bonne_option=1,
        )
        session.add(sondage)
        session.commit()
        session.refresh(sondage)
        session.add(ReponseSondageSeance(
            sondage_id=sondage.id,
            utilisateur_id=eleve_a.id,
            option_index=1,
        ))
        session.commit()
        session.add(ReponseSondageSeance(
            sondage_id=sondage.id,
            utilisateur_id=eleve_a.id,
            option_index=0,
        ))
        with pytest.raises(IntegrityError):
            session.commit()
    engine.dispose()


def test_un_eleve_ne_peut_appartenir_qu_a_une_sous_salle_par_seance():
    engine = creer_base()
    with Session(engine) as session:
        _prof, eleve_a, _eleve_b, _cours, seance = creer_seance(session)
        groupe_a = GroupeSousSalle(
            seance_id=seance.id,
            nom="Groupe 1",
            nom_salle_livekit="interactions-test-groupe-a",
        )
        groupe_b = GroupeSousSalle(
            seance_id=seance.id,
            nom="Groupe 2",
            nom_salle_livekit="interactions-test-groupe-b",
        )
        session.add_all([groupe_a, groupe_b])
        session.commit()
        session.refresh(groupe_a)
        session.refresh(groupe_b)
        session.add(AffectationSousSalle(
            seance_id=seance.id,
            groupe_id=groupe_a.id,
            utilisateur_id=eleve_a.id,
        ))
        session.commit()
        session.add(AffectationSousSalle(
            seance_id=seance.id,
            groupe_id=groupe_b.id,
            utilisateur_id=eleve_a.id,
        ))
        with pytest.raises(IntegrityError):
            session.commit()
    engine.dispose()


def test_consentement_et_transcription_sont_uniques_par_seance():
    engine = creer_base()
    with Session(engine) as session:
        professeur, _eleve_a, _eleve_b, _cours, seance = creer_seance(session)
        session.add(ConsentementTranscription(
            seance_id=seance.id,
            utilisateur_id=professeur.id,
            consenti=True,
        ))
        session.commit()
        session.add(ConsentementTranscription(
            seance_id=seance.id,
            utilisateur_id=professeur.id,
            consenti=False,
        ))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.add(TranscriptionSeance(
            seance_id=seance.id,
            demarree_par_id=professeur.id,
        ))
        session.commit()
        session.add(TranscriptionSeance(
            seance_id=seance.id,
            demarree_par_id=professeur.id,
        ))
        with pytest.raises(IntegrityError):
            session.commit()
    engine.dispose()


def test_routes_interactions_verifient_les_permissions_et_csrf():
    source = (ROOT / "app" / "routers" / "classe_interactions_router.py").read_text(encoding="utf-8")
    assert "Depends(verifier_csrf)" in source
    assert "_est_inscrit(session, cours.id, utilisateur.id)" in source
    assert "AffectationSousSalle.utilisateur_id == utilisateur.id" in source
    assert "StatutDocument.APPROUVE" in source
    assert "document.matiere.strip().casefold()" in source
    assert "ConsentementTranscription.consenti == True" in source
    assert "lister_participants_salle" in source
    assert "arreter_agent_transcription" in source


def test_entree_dans_la_salle_est_bloquee_sans_consentement_si_transcription_active():
    source = (ROOT / "app" / "routers" / "classe_router.py").read_text(encoding="utf-8")
    assert "transcription_active" in source
    assert "ConsentementTranscription.consenti == True" in source
    assert "/transcription/consentement" in source


def test_transcription_stt_sans_enregistrement_audio():
    source = (ROOT / "agents" / "mahay_transcription.py").read_text(encoding="utf-8")
    assert 'agent_name="mahay-transcription"' in source
    assert "groq.STT(" in source
    assert 'model="whisper-large-v3-turbo"' in source
    assert 'language="fr"' in source
    assert "record=False" in source
    readme = (ROOT / "agents" / "README.md").read_text(encoding="utf-8")
    assert "Le worker Mahay n'écrit pas de fichier audio/vidéo" in readme
    assert "`record=False`" in readme
    assert "conditions de traitement du fournisseur Groq" in readme
    assert "LIVEKIT_TRANSCRIPTION_AGENT_NAME" in readme


def test_outils_de_salle_et_post_it_sont_presents():
    salle = (ROOT / "app" / "templates" / "classe_salle.html").read_text(encoding="utf-8")
    assert 'id="btn-sondages"' in salle
    assert 'id="btn-groupes"' in salle
    assert 'id="btn-documents"' in salle
    assert 'id="btn-transcription"' in salle
    assert 'src="/static/classe_interactions.js"' in salle

    tableau = (ROOT / "app" / "templates" / "classe_tableau_fragment.html").read_text(encoding="utf-8")
    assert 'data-outil="note"' in tableau
    assert "d.note" in tableau


def test_templates_groupes_et_consentement_compilent():
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader(ROOT / "app" / "templates"))
    assert env.get_template("classe_sous_salle.html") is not None
    assert env.get_template("classe_transcription_consentement.html") is not None

def test_resultats_sondages_agreges_en_deux_requetes_sans_divulguer_les_votes_ouverts():
    from sqlalchemy import event

    from app.routers.classe_interactions_router import _resultats_sondages

    engine = creer_base()
    nombre_selects = {"total": 0}

    def compter_selects(_connexion, _curseur, instruction, _parametres, _contexte, _executemany):
        if instruction.lstrip().upper().startswith("SELECT"):
            nombre_selects["total"] += 1

    with Session(engine) as session:
        professeur, eleve_a, eleve_b, cours, seance = creer_seance(session)
        professeur_id = professeur.id
        eleve_a_id = eleve_a.id
        eleve_b_id = eleve_b.id
        sondage_ouvert = SondageSeance(
            seance_id=seance.id,
            cours_id=cours.id,
            createur_id=professeur_id,
            question="Question ouverte",
            options_json='["A", "B"]',
            type_sondage="sondage",
            ouvert=True,
        )
        quiz_cloture = SondageSeance(
            seance_id=seance.id,
            cours_id=cours.id,
            createur_id=professeur.id,
            question="Question terminée",
            options_json='["Faux", "Vrai"]',
            type_sondage="quiz",
            bonne_option=1,
            ouvert=False,
        )
        session.add_all([sondage_ouvert, quiz_cloture])
        session.commit()
        session.refresh(sondage_ouvert)
        session.refresh(quiz_cloture)
        session.add_all([
            ReponseSondageSeance(
                sondage_id=sondage_ouvert.id,
                utilisateur_id=eleve_a_id,
                option_index=0,
            ),
            ReponseSondageSeance(
                sondage_id=sondage_ouvert.id,
                utilisateur_id=eleve_b_id,
                option_index=1,
            ),
            ReponseSondageSeance(
                sondage_id=quiz_cloture.id,
                utilisateur_id=eleve_a.id,
                option_index=1,
            ),
        ])
        session.commit()
        session.refresh(sondage_ouvert)
        session.refresh(quiz_cloture)

        event.listen(engine, "before_cursor_execute", compter_selects)
        try:
            resultats_eleve = _resultats_sondages(
                session,
                [sondage_ouvert, quiz_cloture],
                eleve_a_id,
                False,
            )
            assert nombre_selects["total"] == 2

            ouvert, cloture = resultats_eleve
            assert ouvert["a_repondu"] is True
            assert ouvert["ma_reponse"] == 0
            assert ouvert["nombre_reponses"] == 2
            assert ouvert["comptes"] is None
            assert ouvert["bonne_option"] is None

            assert cloture["a_repondu"] is True
            assert cloture["ma_reponse"] == 1
            assert cloture["nombre_reponses"] == 1
            assert cloture["comptes"] == [0, 1]
            assert cloture["bonne_option"] == 1

            resultats_prof = _resultats_sondages(
                session,
                [sondage_ouvert, quiz_cloture],
                professeur_id,
                True,
            )
            assert nombre_selects["total"] == 4
            assert resultats_prof[0]["comptes"] == [1, 1]
            assert resultats_prof[1]["bonne_option"] == 1
        finally:
            event.remove(engine, "before_cursor_execute", compter_selects)

    engine.dispose()

def test_lister_sous_salles_charge_affectations_et_noms_en_lot():
    from sqlalchemy import event

    from app.routers.classe_interactions_router import _resultats_groupes_sous_salles

    engine = creer_base()
    nombre_selects = {"total": 0}

    def compter_selects(_connexion, _curseur, instruction, _parametres, _contexte, _executemany):
        if instruction.lstrip().upper().startswith("SELECT"):
            nombre_selects["total"] += 1

    with Session(engine) as session:
        professeur, eleve_a, eleve_b, _cours, seance = creer_seance(session)
        seance_id = seance.id
        professeur_id = professeur.id
        eleve_a_id = eleve_a.id
        eleve_b_id = eleve_b.id
        eleve_c = creer_utilisateur("Élève C", "+261340000904", RoleUtilisateur.ETUDIANT)
        session.add(eleve_c)
        session.commit()
        session.refresh(eleve_c)
        eleve_c_id = eleve_c.id
        groupe_a = GroupeSousSalle(
            seance_id=seance_id,
            nom="Groupe 1",
            nom_salle_livekit="sous-salle-batch-1",
        )
        groupe_b = GroupeSousSalle(
            seance_id=seance_id,
            nom="Groupe 2",
            nom_salle_livekit="sous-salle-batch-2",
        )
        session.add_all([groupe_a, groupe_b])
        session.commit()
        session.refresh(groupe_a)
        session.refresh(groupe_b)
        groupe_a_id = groupe_a.id
        groupe_b_id = groupe_b.id
        session.add_all([
            AffectationSousSalle(
                seance_id=seance_id,
                groupe_id=groupe_a_id,
                utilisateur_id=eleve_a_id,
            ),
            AffectationSousSalle(
                seance_id=seance_id,
                groupe_id=groupe_a_id,
                utilisateur_id=eleve_b_id,
            ),
            AffectationSousSalle(
                seance_id=seance_id,
                groupe_id=groupe_b_id,
                utilisateur_id=eleve_c_id,
            ),
        ])
        session.commit()
        groupes = session.exec(
            select(GroupeSousSalle)
            .where(GroupeSousSalle.seance_id == seance_id)
            .order_by(GroupeSousSalle.id)
        ).all()

        event.listen(engine, "before_cursor_execute", compter_selects)
        try:
            resultats_prof = _resultats_groupes_sous_salles(
                session,
                seance_id,
                groupes,
                professeur_id,
                True,
            )
            assert nombre_selects["total"] == 2
            assert [g["nombre_membres"] for g in resultats_prof] == [2, 1]
            assert resultats_prof[0]["membres"] == ["Élève A", "Élève B"]
            assert resultats_prof[1]["membres"] == ["Élève C"]

            resultats_eleve = _resultats_groupes_sous_salles(
                session,
                seance_id,
                groupes,
                eleve_a_id,
                False,
            )
            assert nombre_selects["total"] == 3
            assert len(resultats_eleve) == 1
            assert resultats_eleve[0]["id"] == groupe_a_id
            assert resultats_eleve[0]["membres"] == []
            assert resultats_eleve[0]["est_mon_groupe"] is True
        finally:
            event.remove(engine, "before_cursor_execute", compter_selects)

    engine.dispose()



def test_recreer_sous_salles_remplace_groupes_et_affectations_en_lot():
    from sqlalchemy import event

    from app.routers.classe_interactions_router import _remplacer_groupes_sous_salles

    engine = creer_base()
    compteurs = {"select": 0, "delete": 0}

    def compter_lectures_et_suppressions(
        _connexion, _curseur, instruction, _parametres, _contexte, _executemany
    ):
        commande = instruction.lstrip().split(None, 1)[0].upper()
        if commande == "SELECT":
            compteurs["select"] += 1
        elif commande == "DELETE":
            compteurs["delete"] += 1

    with Session(engine) as session:
        _prof, eleve_a, eleve_b, _cours, seance = creer_seance(session)
        seance_id = seance.id
        nom_salle_livekit = seance.nom_salle_livekit
        eleve_a_id = eleve_a.id
        eleve_b_id = eleve_b.id
        eleve_c = creer_utilisateur("Élève C", "+261340000905", RoleUtilisateur.ETUDIANT)
        session.add(eleve_c)
        session.commit()
        session.refresh(eleve_c)
        eleve_c_id = eleve_c.id

        anciens = [
            GroupeSousSalle(
                seance_id=seance_id,
                nom=f"Ancien {index + 1}",
                nom_salle_livekit=f"ancienne-salle-{index + 1}",
            )
            for index in range(3)
        ]
        session.add_all(anciens)
        session.commit()
        for ancien in anciens:
            session.refresh(ancien)
        anciens_ids = {ancien.id for ancien in anciens}
        session.add_all([
            AffectationSousSalle(
                seance_id=seance_id,
                groupe_id=anciens[0].id,
                utilisateur_id=eleve_a_id,
            ),
            AffectationSousSalle(
                seance_id=seance_id,
                groupe_id=anciens[1].id,
                utilisateur_id=eleve_b_id,
            ),
            AffectationSousSalle(
                seance_id=seance_id,
                groupe_id=anciens[2].id,
                utilisateur_id=eleve_c_id,
            ),
        ])
        session.commit()

        event.listen(engine, "before_cursor_execute", compter_lectures_et_suppressions)
        try:
            _remplacer_groupes_sous_salles(
                session,
                seance_id,
                nom_salle_livekit,
                2,
                [eleve_a_id, eleve_b_id, eleve_c_id],
            )
        finally:
            event.remove(engine, "before_cursor_execute", compter_lectures_et_suppressions)

        assert compteurs == {"select": 0, "delete": 2}
        nouveaux_groupes = session.exec(
            select(GroupeSousSalle)
            .where(GroupeSousSalle.seance_id == seance_id)
            .order_by(GroupeSousSalle.id)
        ).all()
        affectations = session.exec(
            select(AffectationSousSalle).where(
                AffectationSousSalle.seance_id == seance_id
            )
        ).all()

        assert [groupe.nom for groupe in nouveaux_groupes] == ["Groupe 1", "Groupe 2"]
        assert len(affectations) == 3
        assert {affectation.groupe_id for affectation in affectations} == {
            groupe.id for groupe in nouveaux_groupes
        }
        assert {affectation.utilisateur_id for affectation in affectations} == {
            eleve_a_id, eleve_b_id, eleve_c_id
        }
        assert {affectation.groupe_id for affectation in affectations}.isdisjoint(
            anciens_ids
        )

    engine.dispose()
