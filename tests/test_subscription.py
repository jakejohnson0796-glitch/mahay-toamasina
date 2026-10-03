from datetime import datetime, timedelta

from app.models import AbonnementEtudiant, StatutAbonnementEtudiant
from app import subscription


def _abonnement_essai(jours_ecoules: int = 0) -> AbonnementEtudiant:
    debut = datetime.utcnow() - timedelta(days=jours_ecoules)
    return AbonnementEtudiant(
        utilisateur_id=1,
        statut=StatutAbonnementEtudiant.ESSAI,
        date_debut_essai=debut,
        date_fin_essai=debut + timedelta(days=subscription.DUREE_ESSAI_JOURS),
    )


def test_essai_general_dure_soixante_jours():
    assert subscription.DUREE_ESSAI_JOURS == 60
    assert subscription.DUREE_ESSAI_IA_JOURS == 14


def test_ia_est_accessible_pendant_les_quatorze_premiers_jours():
    abonnement = _abonnement_essai(jours_ecoules=13)

    assert subscription.acces_premium_valide(abonnement) is True
    assert subscription.acces_ia_valide(abonnement) is True


def test_ia_expire_apres_quatorze_jours_mais_premium_reste_actif():
    abonnement = _abonnement_essai(jours_ecoules=15)

    assert subscription.acces_premium_valide(abonnement) is True
    assert subscription.acces_ia_valide(abonnement) is False


def test_abonnement_paye_actif_redonne_acces_a_l_ia():
    maintenant = datetime.utcnow()
    abonnement = AbonnementEtudiant(
        utilisateur_id=1,
        statut=StatutAbonnementEtudiant.ACTIF,
        date_debut_essai=maintenant - timedelta(days=30),
        date_fin_essai=maintenant + timedelta(days=30),
        date_fin_abonnement=maintenant + timedelta(days=30),
    )

    assert subscription.acces_ia_valide(abonnement) is True


def test_compteur_ia_egal_zero_hors_fenetre():
    abonnement = _abonnement_essai(jours_ecoules=15)

    assert subscription.jours_restants_ia(abonnement) == 0
