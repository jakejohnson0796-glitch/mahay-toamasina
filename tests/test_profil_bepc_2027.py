from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.responses import RedirectResponse

from app.routers import quiz_router


ROOT = Path(__file__).resolve().parents[1]


class FakeSession:
    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.commits += 1


@pytest.mark.parametrize("parcours", ["pe", "ps_a", "ps_b"])
def test_un_eleve_de_3e_peut_enregistrer_son_programme_bepc(parcours, monkeypatch):
    utilisateur = SimpleNamespace(id=12, bepc_2027_parcours=None)
    session = FakeSession()
    contexte = {"cycle_education": "college", "niveau": "3e"}

    monkeypatch.setattr(
        quiz_router, "utilisateur_courant",
        lambda request, db: utilisateur,
    )
    monkeypatch.setattr(
        quiz_router, "acces_ia_ou_redirection",
        lambda current, db: None,
    )
    monkeypatch.setattr(
        quiz_router, "_contexte_scolaire_quiz",
        lambda current, db: contexte,
    )

    reponse = quiz_router.enregistrer_programme_bepc_2027(
        SimpleNamespace(), parcours, session, None
    )

    assert isinstance(reponse, RedirectResponse)
    assert reponse.status_code == 303
    assert reponse.headers["location"] == "/objectif-examen?ok=programme_bepc_enregistre"
    assert utilisateur.bepc_2027_parcours == parcours
    assert session.added == [utilisateur]
    assert session.commits == 1


def test_refuse_de_modifier_le_programme_hors_classe_de_3e(monkeypatch):
    utilisateur = SimpleNamespace(id=12, bepc_2027_parcours=None)
    session = FakeSession()

    monkeypatch.setattr(
        quiz_router, "utilisateur_courant",
        lambda request, db: utilisateur,
    )
    monkeypatch.setattr(
        quiz_router, "acces_ia_ou_redirection",
        lambda current, db: None,
    )
    monkeypatch.setattr(
        quiz_router, "_contexte_scolaire_quiz",
        lambda current, db: {"cycle_education": "college", "niveau": "4e"},
    )

    reponse = quiz_router.enregistrer_programme_bepc_2027(
        SimpleNamespace(), "ps_a", session, None
    )

    assert reponse.status_code == 303
    assert reponse.headers["location"] == "/objectif-examen?erreur=programme_bepc_invalide"
    assert utilisateur.bepc_2027_parcours is None
    assert session.commits == 0


def test_refuse_de_modifier_le_programme_sans_authentification_ia(monkeypatch):
    utilisateur = SimpleNamespace(id=12, bepc_2027_parcours=None)
    session = FakeSession()
    redirection = RedirectResponse("/abonnement", status_code=303)

    monkeypatch.setattr(
        quiz_router, "utilisateur_courant",
        lambda request, db: utilisateur,
    )
    monkeypatch.setattr(
        quiz_router, "acces_ia_ou_redirection",
        lambda current, db: redirection,
    )

    reponse = quiz_router.enregistrer_programme_bepc_2027(
        SimpleNamespace(), "pe", session, None
    )

    assert reponse is redirection
    assert utilisateur.bepc_2027_parcours is None
    assert session.commits == 0


def test_mode_examen_utilise_le_programme_du_profil_et_non_un_post_libre():
    route = (
        ROOT / "app/routers/quiz_router.py"
    ).read_text(encoding="utf-8")
    section = route.split('@router.post("/objectif-examen/lancer")', 1)[1].split(
        '@router.get("/quiz")', 1
    )[0]

    assert 'getattr(utilisateur, "bepc_2027_parcours", None)' in section
    assert 'option_attendue = {"ps_a": "A", "ps_b": "B"}.get(parcours_profil)' in section
    assert "objectif, option_ps=option_attendue" in section
    assert "option_ps.strip().upper() != (option_attendue or '')" in section


def test_modele_et_migration_conservent_les_anciens_profils():
    modele = (ROOT / "app/models.py").read_text(encoding="utf-8")
    utilisateur = modele.split("class Utilisateur(SQLModel, table=True):", 1)[1].split(
        "class ", 1
    )[0]
    assert "bepc_2027_parcours" in utilisateur
    assert "default=None" in utilisateur

    migration = (
        ROOT
        / "alembic/versions/m1e7b3c5d9a2_profil_bepc_2027_parcours.py"
    ).read_text(encoding="utf-8")
    assert 'revision: str = "m1e7b3c5d9a2"' in migration
    assert 'down_revision: Union[str, Sequence[str], None] = "l6d8b2f1a4c9"' in migration
    assert '"bepc_2027_parcours"' in migration
    assert "nullable=True" in migration
    assert "ix_utilisateur_bepc_2027_parcours" in migration


def test_page_et_route_expliquent_que_le_choix_est_declare_et_filtre():
    template = (ROOT / "app/templates/objectif_examen.html").read_text(encoding="utf-8")
    route = (ROOT / "app/routers/quiz_router.py").read_text(encoding="utf-8")

    assert 'action="/objectif-examen/programme"' in template
    assert 'name="parcours"' in template
    assert "n'est pas présenté comme une vérification officielle" in template
    assert "bepc_parcours=bepc_programme_actuel" in route
    assert "Document.annee != 2027" in route
