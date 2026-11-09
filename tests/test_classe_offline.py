from datetime import datetime
from types import SimpleNamespace

from app.classe_offline import construire_pack_hors_ligne


def test_pack_hors_ligne_contient_uniquement_le_contenu_pedagogique_partage():
    cours = SimpleNamespace(id=12, nom="Mathématiques", matiere="Algèbre", niveau="L1",
                            description="Introduction", objectifs="Comprendre les matrices")
    seance = SimpleNamespace(id=3, titre="Matrices", description="Cours de base",
                             statut=SimpleNamespace(value="terminee"),
                             date_creation=datetime(2026, 11, 1, 9, 0))
    devoir = SimpleNamespace(id=7, titre="Exercice 1", description="Calculer un déterminant",
                             date_limite=datetime(2026, 11, 20, 12, 0), bareme=20,
                             coefficient=1.5, periode="Semestre 1", est_clos=False)
    pack = construire_pack_hors_ligne(cours, [seance], [devoir])
    assert pack["schema_version"] == 1
    assert pack["cours"]["id"] == 12
    assert pack["cours"]["objectifs"] == "Comprendre les matrices"
    assert pack["seances"][0]["statut"] == "terminee"
    assert pack["devoirs"][0]["bareme"] == 20.0
    assert "notes" not in pack and "rendus" not in pack
    assert "utilisateur" not in pack


def test_pack_hors_ligne_limite_seances_et_devoirs():
    cours = SimpleNamespace(id=1, nom="Cours", matiere="Matière", niveau="N1",
                            description="", objectifs="")
    seance = SimpleNamespace(id=1, titre="Séance", description="", statut="planifiee",
                             date_creation=None)
    devoir = SimpleNamespace(id=1, titre="Devoir", description="", date_limite=None,
                             bareme=10, coefficient=1, periode="", est_clos=False)
    pack = construire_pack_hors_ligne(cours, [seance]*105, [devoir]*107)
    assert len(pack["seances"]) == 100
    assert len(pack["devoirs"]) == 100
    assert pack["limites"] == {"seances_tronquees": True, "devoirs_tronques": True}


def test_pack_hors_ligne_n_expose_aucune_note_presence_ou_information_de_compte():
    cours = SimpleNamespace(id=2, nom="Histoire", matiere="Histoire", niveau="Terminale",
                            description="", objectifs="")
    pack = construire_pack_hors_ligne(cours, [], [])
    contenu = str(pack).lower()
    assert "note" not in contenu
    assert "presence" not in contenu
    assert "mot_de_passe" not in contenu


def test_export_pack_refuse_un_visiteur_non_connecte(monkeypatch):
    from types import SimpleNamespace
    from app.routers import classe_router

    monkeypatch.setattr(classe_router, "utilisateur_courant", lambda _request, _session: None)
    response = classe_router.exporter_pack_cours_hors_ligne(
        SimpleNamespace(), 5, SimpleNamespace()
    )
    assert response.status_code == 401
    assert response.headers["cache-control"] == "private, no-store"


def test_export_pack_refuse_un_apprenant_non_inscrit(monkeypatch):
    from types import SimpleNamespace
    from app.routers import classe_router

    utilisateur = SimpleNamespace(id=42)
    cours = SimpleNamespace(id=5, professeur_id=1)

    class FausseSession:
        def get(self, _model, _identifiant):
            return cours

    monkeypatch.setattr(classe_router, "utilisateur_courant", lambda _request, _session: utilisateur)
    monkeypatch.setattr(classe_router, "_peut_gerer_cours", lambda _cours, _user: False)
    monkeypatch.setattr(classe_router, "_est_inscrit", lambda _session, _cours, _user: False)
    response = classe_router.exporter_pack_cours_hors_ligne(
        SimpleNamespace(), 5, FausseSession()
    )
    assert response.status_code == 403
    assert response.headers["cache-control"] == "private, no-store"


def test_export_pack_autorise_un_inscrit_et_ne_cache_pas_la_reponse(monkeypatch):
    from types import SimpleNamespace
    from app.routers import classe_router

    utilisateur = SimpleNamespace(id=42)
    cours = SimpleNamespace(
        id=5, professeur_id=1, nom="Maths", matiere="Algèbre", niveau="L1",
        description="", objectifs="",
    )

    class Resultat:
        def all(self):
            return []

    class FausseSession:
        def get(self, _model, _identifiant):
            return cours

        def exec(self, _requete):
            return Resultat()

    monkeypatch.setattr(classe_router, "utilisateur_courant", lambda _request, _session: utilisateur)
    monkeypatch.setattr(classe_router, "_peut_gerer_cours", lambda _cours, _user: False)
    monkeypatch.setattr(classe_router, "_est_inscrit", lambda _session, _cours, _user: True)
    response = classe_router.exporter_pack_cours_hors_ligne(
        SimpleNamespace(), 5, FausseSession()
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["vary"] == "Cookie"
    assert b'"schema_version":1' in response.body
