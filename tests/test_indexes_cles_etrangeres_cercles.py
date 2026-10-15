"""Garde-fous sur les index des tables de Cercles."""

from app.models import (
    CercleEtude,
    DemandeAdhesionCercle,
    DemandeCreationCercle,
    MessageCercle,
    MessageReaction,
    SignalementMessage,
    ThemeDuJour,
)


def test_foreign_key_indexes_for_study_circle_tables_are_declared():
    attendus = {
        CercleEtude: {"ix_cercleetude_createur_id", "ix_cercleetude_filiere_id"},
        DemandeAdhesionCercle: {
            "ix_demandeadhesioncercle_traite_par_id",
            "ix_demandeadhesioncercle_utilisateur_id",
        },
        DemandeCreationCercle: {
            "ix_demandecreationcercle_cercle_cree_id",
            "ix_demandecreationcercle_filiere_id",
            "ix_demandecreationcercle_traite_par_id",
            "ix_demandecreationcercle_utilisateur_id",
        },
        MessageCercle: {"ix_messagecercle_auteur_id", "ix_messagecercle_epingle_par_id"},
        MessageReaction: {"ix_messagereaction_utilisateur_id"},
        SignalementMessage: {"ix_signalementmessage_signale_par_id"},
        ThemeDuJour: {"ix_themedujour_cercle_id"},
    }
    for modele, indexes_attendus in attendus.items():
        indexes_declares = {index.name for index in modele.__table__.indexes}
        assert indexes_attendus <= indexes_declares, (
            modele.__name__,
            indexes_attendus - indexes_declares,
        )
