from app.models import MembreEtablissement, RoleMembreEtablissement, StatutMembreEtablissement
from app.routers.institution_router import peut_gerer_role, roles_assignables


def test_membre_etablissement_est_unique_par_institution_et_compte():
    constraints = {c.name for c in MembreEtablissement.__table__.constraints}
    assert "uq_membre_etablissement_institution_utilisateur" in constraints


def test_membre_etablissement_expose_un_index_de_recherche_par_role_et_statut():
    indexes = {index.name for index in MembreEtablissement.__table__.indexes}
    assert "ix_membre_etablissement_institution_role_statut" in indexes


def test_roles_locaux_ne_donnent_pas_de_droits_administrateur_global():
    assert roles_assignables("responsable") == ["gestionnaire", "enseignant", "etudiant"]
    assert "responsable" not in roles_assignables("responsable")
    assert roles_assignables("gestionnaire") == ["enseignant", "etudiant"]
    assert roles_assignables("enseignant") == []
    assert roles_assignables("etudiant") == []
    assert roles_assignables(None, administrateur_global=True) == [
        "responsable", "gestionnaire", "enseignant", "etudiant"
    ]


def test_gestionnaire_ne_peut_pas_modifier_un_responsable_ou_un_gestionnaire():
    assert peut_gerer_role("gestionnaire", "enseignant") is True
    assert peut_gerer_role("gestionnaire", "etudiant") is True
    assert peut_gerer_role("gestionnaire", "gestionnaire") is False
    assert peut_gerer_role("gestionnaire", "responsable") is False


def test_responsable_peut_gerer_les_gestionnaires_et_roles_inferieurs():
    assert peut_gerer_role("responsable", "gestionnaire") is True
    assert peut_gerer_role("responsable", "enseignant") is True
    assert peut_gerer_role("responsable", "etudiant") is True
    assert peut_gerer_role("responsable", "responsable") is False


def test_admin_global_peut_gerer_tous_les_roles_locaux():
    assert peut_gerer_role("admin", "responsable", administrateur_global=True) is True


def test_enum_roles_membre_est_clair_et_stable():
    assert RoleMembreEtablissement.RESPONSABLE.value == "responsable"
    assert RoleMembreEtablissement.ETUDIANT.value == "etudiant"
    assert StatutMembreEtablissement.ACTIF.value == "actif"
    assert StatutMembreEtablissement.SUSPENDU.value == "suspendu"
