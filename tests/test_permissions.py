from types import SimpleNamespace

from app.models import RoleUtilisateur
from app.permissions import (
    Permission,
    est_administrateur_global,
    has_permission,
    peut_gerer_cours,
    peut_gerer_role_institution,
    peut_voir_enfant,
    professeur_approuve,
    roles_institution_assignables,
)


def _professeur(*, identifiant=10, statut="approuve", profil="professeur"):
    return SimpleNamespace(
        id=identifiant,
        role=RoleUtilisateur.PROFESSEUR,
        profil_souhaite=profil,
        statut_verification_enseignant=statut,
        banni=False,
    )


def _etudiant(*, identifiant=20):
    return SimpleNamespace(
        id=identifiant,
        role=RoleUtilisateur.ETUDIANT,
        profil_souhaite="eleve",
        banni=False,
    )


def test_administrateur_global_est_reconnu_mais_un_admin_banni_ne_l_est_pas():
    admin = SimpleNamespace(role=RoleUtilisateur.ADMIN, banni=False)
    admin_banni = SimpleNamespace(role=RoleUtilisateur.ADMIN, banni=True)

    assert est_administrateur_global(admin)
    assert has_permission(admin, Permission.PLATFORM_SECURITY_MANAGE)
    assert not est_administrateur_global(admin_banni)
    assert not has_permission(admin_banni, Permission.PLATFORM_SECURITY_MANAGE)


def test_professeur_doit_avoir_un_role_effectif_et_une_approbation_active():
    assert professeur_approuve(_professeur())
    assert not professeur_approuve(_professeur(statut="en_attente"))
    assert not professeur_approuve(_professeur(statut="retire"))
    # Le profil demandé à l'inscription n'est pas un droit : seul le rôle
    # effectif attribué après validation et son statut gouvernent l'accès.
    assert professeur_approuve(_professeur(profil="eleve"))
    compte_sans_role = SimpleNamespace(
        id=11,
        role=RoleUtilisateur.ETUDIANT,
        profil_souhaite="professeur",
        statut_verification_enseignant="approuve",
        banni=False,
    )
    assert not professeur_approuve(compte_sans_role)


def test_gestion_cours_exige_a_la_fois_approbation_et_propriete():
    cours = SimpleNamespace(id=4, professeur_id=10)

    assert peut_gerer_cours(cours, _professeur(identifiant=10))
    assert not peut_gerer_cours(cours, _professeur(identifiant=11))
    assert not peut_gerer_cours(cours, _professeur(identifiant=10, statut="en_attente"))
    assert not peut_gerer_cours(cours, _etudiant())


def test_demande_professeur_en_attente_ne_recoit_aucune_permission_enseignant():
    candidat = SimpleNamespace(
        id=30,
        role=RoleUtilisateur.ETUDIANT,
        profil_souhaite="professeur",
        statut_verification_enseignant="en_attente",
        banni=False,
    )
    assert not has_permission(candidat, Permission.TEACHING_TOOLS)
    assert not has_permission(candidat, Permission.TEACHING_UPDATE_SUBMIT)


def test_permission_inconnue_est_refusee_par_defaut():
    assert not has_permission(_etudiant(), "platform.super-secret")


def test_hierarchie_institutionnelle_interdit_les_escalades():
    assert roles_institution_assignables("responsable") == [
        "gestionnaire", "enseignant", "etudiant"
    ]
    assert roles_institution_assignables("gestionnaire") == [
        "enseignant", "etudiant"
    ]
    assert roles_institution_assignables("enseignant") == []
    assert peut_gerer_role_institution("responsable", "gestionnaire")
    assert peut_gerer_role_institution("gestionnaire", "enseignant")
    assert not peut_gerer_role_institution("gestionnaire", "gestionnaire")
    assert not peut_gerer_role_institution("gestionnaire", "responsable")


class _Resultat:
    def __init__(self, valeur):
        self.valeur = valeur

    def first(self):
        return self.valeur


class _SessionFamille:
    def __init__(self, enfant, lien):
        self.enfant = enfant
        self.lien = lien

    def get(self, _modele, identifiant):
        return self.enfant if identifiant == self.enfant.id else None

    def exec(self, _requete):
        return _Resultat(self.lien)


def test_portail_famille_exige_un_lien_actif_et_un_responsable_approuve():
    responsable = SimpleNamespace(
        id=1,
        role=RoleUtilisateur.RESPONSABLE,
        profil_souhaite="responsable",
        statut_verification_responsable="approuve",
        banni=False,
    )
    enfant = _etudiant(identifiant=2)

    assert peut_voir_enfant(_SessionFamille(enfant, object()), responsable, 2)
    assert not peut_voir_enfant(_SessionFamille(enfant, None), responsable, 2)

    responsable_non_approuve = SimpleNamespace(
        id=1,
        role=RoleUtilisateur.RESPONSABLE,
        profil_souhaite="responsable",
        statut_verification_responsable="en_attente",
        banni=False,
    )
    assert not peut_voir_enfant(_SessionFamille(enfant, object()), responsable_non_approuve, 2)

def test_admin_global_ne_contourne_pas_les_liens_familiaux():
    admin = SimpleNamespace(role=RoleUtilisateur.ADMIN, banni=False)
    assert not has_permission(admin, Permission.FAMILY_PORTAL_VIEW)
    assert not has_permission(
        admin,
        Permission.FAMILY_CHILD_VIEW,
        session=object(),
        child_id=2,
    )
