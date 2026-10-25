from pathlib import Path
from types import SimpleNamespace

from app import ai_quiz
from app.models import StatutTacheIA
from app.routers import tuteur_router


ROOT = Path(__file__).resolve().parents[1]


def test_diagnostic_tuteur_reformule_les_points_sans_restituer_le_texte_du_critique():
    texte_brut = "Le calcul du déterminant est faux; la correction contredit les données de l'exercice secret."
    audit = {
        "critics": [
            {
                "avis": {
                    "confiant": False,
                    "problemes": [texte_brut],
                    "ameliorations": ["réexplique les étapes de calcul"],
                }
            }
        ]
    }

    resume = ai_quiz._diagnostic_pedagogique_verification_tuteur(audit)

    assert "Points à reprendre :" in resume
    assert "calculs" in resume.lower()
    assert "cohérence" in resume.lower()
    assert texte_brut not in resume
    assert "secret" not in resume


def test_verification_tuteur_a_revoir_enregistre_un_diagnostic_sûr(monkeypatch):
    audit = {
        "models": ["critic-a"],
        "critics": [
            {
                "model": "critic-a",
                "avis": {
                    "confiant": False,
                    "problemes": ["Le calcul est à revérifier et la correction ne correspond pas à l'exercice."],
                    "ameliorations": [],
                },
            }
        ],
    }
    monkeypatch.setattr(
        ai_quiz.ai_ensemble,
        "verifier_tuteur",
        lambda **_kwargs: (
            {"explication": "Explication", "exemple": "Exemple", "exercice": "Exercice", "correction": "Correction"},
            False,
            audit,
        ),
    )
    monkeypatch.setattr(ai_quiz.ai_memory, "enregistrer_audit_ensemble", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(ai_quiz.parametres, "ai_ensemble_enabled", True)

    resultat = ai_quiz.verifier_reponse_tuteur_structuree(
        {"explication": "Explication", "exemple": "Exemple", "exercice": "Exercice", "correction": "Correction"},
        question="Question de test",
        notion="Déterminant",
        matiere="Mathématiques",
        strategie="renforcee",
    )

    assert resultat["_statut_verification"] == "a_revoir"
    assert resultat["_verification_ok"] is False
    assert "Points à reprendre :" in resultat["_erreur_verification"]
    assert "Le calcul est à revérifier" not in resultat["_erreur_verification"]


def test_absence_de_retour_des_correcteurs_est_une_indisponibilite_pas_un_desaccord(monkeypatch):
    monkeypatch.setattr(
        ai_quiz.ai_ensemble,
        "verifier_tuteur",
        lambda **_kwargs: (
            {"explication": "Explication", "exemple": "Exemple", "exercice": "Exercice", "correction": "Correction"},
            False,
            {"models": ["critic-a"], "critics": []},
        ),
    )
    monkeypatch.setattr(ai_quiz.ai_memory, "enregistrer_audit_ensemble", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(ai_quiz.parametres, "ai_ensemble_enabled", True)

    resultat = ai_quiz.verifier_reponse_tuteur_structuree(
        {"explication": "Explication", "exemple": "Exemple", "exercice": "Exercice", "correction": "Correction"},
        question="Question de test",
        notion=None,
        matiere="Mathématiques",
        strategie="legere",
    )

    assert resultat["_statut_verification"] == "echouee"
    assert "pas fourni d'avis exploitable" in resultat["_erreur_verification"]


class _ResultatFaux:
    def __init__(self, valeur):
        self.valeur = valeur

    def first(self):
        return self.valeur


class _SessionVerificationFausse:
    def __init__(self, session_tuteur, tache):
        self.lignes = [session_tuteur, tache]
        self.ajoutes = []
        self.commit_count = 0

    def exec(self, _requete):
        return _ResultatFaux(self.lignes.pop(0))

    def add(self, valeur):
        self.ajoutes.append(valeur)

    def commit(self):
        self.commit_count += 1


def _session_tuteur_a_revoir(essais=1):
    return SimpleNamespace(
        id=51,
        utilisateur_id=7,
        statut_verification_ia="a_revoir",
        erreur_verification_ia=(
            "La vérification n'a pas confirmé tous les points pédagogiques. "
            "Points à reprendre : Les calculs doivent être revérifiés."
        ),
        date_verification_ia=None,
    )


def _tache_verification(essais=1, statut=StatutTacheIA.TERMINEE):
    return SimpleNamespace(
        id=90,
        type_tache="verification_tuteur",
        session_tuteur_id=51,
        statut=statut,
        nombre_essais=essais,
        strategie_verification="legere",
        disponible_le=None,
        prise_en_charge_le=None,
        terminee_le=None,
        derniere_erreur=None,
    )


def test_relance_tuteur_justifiee_est_unique_et_utilise_le_controle_renforce(monkeypatch):
    session_tuteur = _session_tuteur_a_revoir()
    tache = _tache_verification()
    db = _SessionVerificationFausse(session_tuteur, tache)
    notifications = []

    monkeypatch.setattr(tuteur_router, "utilisateur_courant", lambda _request, _session: SimpleNamespace(id=7))
    monkeypatch.setattr(tuteur_router, "acces_ia_ou_redirection", lambda _utilisateur, _session: None)
    monkeypatch.setattr(tuteur_router, "limite_depassee", lambda *_args: False)
    monkeypatch.setattr(tuteur_router.ai_queue, "notifier_tache", lambda task_id: notifications.append(task_id) or True)

    response = tuteur_router.relancer_verification_tuteur_session(
        SimpleNamespace(),
        51,
        session=db,
        _csrf=None,
    )

    assert response.status_code == 303
    assert "verification=relancee" in response.headers["location"]
    assert session_tuteur.statut_verification_ia == "en_attente"
    assert session_tuteur.erreur_verification_ia is None
    assert tache.statut == StatutTacheIA.EN_ATTENTE
    assert tache.strategie_verification == "renforcee"
    assert tache.nombre_essais == 1
    assert tache.disponible_le is not None
    assert tache.terminee_le is None
    assert db.commit_count == 1
    assert notifications == [90]


def test_relance_tuteur_refuse_les_taches_ayant_deja_consomme_plusieurs_essais(monkeypatch):
    session_tuteur = _session_tuteur_a_revoir()
    tache = _tache_verification(essais=2)
    db = _SessionVerificationFausse(session_tuteur, tache)
    notifications = []

    monkeypatch.setattr(tuteur_router, "utilisateur_courant", lambda _request, _session: SimpleNamespace(id=7))
    monkeypatch.setattr(tuteur_router, "acces_ia_ou_redirection", lambda _utilisateur, _session: None)
    monkeypatch.setattr(tuteur_router, "limite_depassee", lambda *_args: False)
    monkeypatch.setattr(tuteur_router.ai_queue, "notifier_tache", lambda task_id: notifications.append(task_id) or True)

    response = tuteur_router.relancer_verification_tuteur_session(
        SimpleNamespace(),
        51,
        session=db,
        _csrf=None,
    )

    assert response.status_code == 303
    assert "verification=non_disponible" in response.headers["location"]
    assert session_tuteur.statut_verification_ia == "a_revoir"
    assert tache.statut == StatutTacheIA.TERMINEE
    assert db.commit_count == 0
    assert notifications == []


def test_template_explique_le_statut_et_limite_la_relance_a_un_seul_controle():
    template = (ROOT / "app" / "templates" / "tuteur_reponse.html").read_text(encoding="utf-8")

    assert "Pourquoi la réponse est-elle « à revoir » ?" in template
    assert "Points à reprendre" in template
    assert "Faire une vérification renforcée (une seule fois)" in template
    assert 'action="/tuteur/{{ session_tuteur.id }}/relancer-verification"' in template
    assert "ne sera pas relancé en boucle" in template
