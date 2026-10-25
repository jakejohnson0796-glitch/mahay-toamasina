"""Add covering indexes for foreign keys flagged by the production advisor.

These application tables are currently small. Indexes are added through a normal
Alembic transaction so each index is complete before the migration succeeds.
The targeted columns are the 41 foreign keys identified without a covering
B-tree index by the Supabase performance advisor on 2026-10-25.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "c4e8a1d9b7f2"
down_revision: Union[str, None] = "f6b1a2c9d4e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_INDEXES: tuple[tuple[str, str, str], ...] = (
    ("ix_fk_abonnement_utilisateur_id", "abonnement", "utilisateur_id"),
    ("ix_fk_abonnementetudiant_valide_par_admin_id", "abonnementetudiant", "valide_par_admin_id"),
    ("ix_fk_autorisationecrituretableau_utilisateur_id", "autorisationecrituretableau", "utilisateur_id"),
    ("ix_fk_codereinitialisationmotdepasse_utilisateur_id", "codereinitialisationmotdepasse", "utilisateur_id"),
    ("ix_fk_codesecours2fa_utilisateur_id", "codesecours2fa", "utilisateur_id"),
    ("ix_fk_consultationdocument_document_id", "consultationdocument", "document_id"),
    ("ix_fk_consultationdocument_utilisateur_id", "consultationdocument", "utilisateur_id"),
    ("ix_fk_cours_professeur_id", "cours", "professeur_id"),
    ("ix_fk_demandechangementfiliere_ancienne_filiere_id", "demandechangementfiliere", "ancienne_filiere_id"),
    ("ix_fk_demandechangementfiliere_nouvelle_filiere_id", "demandechangementfiliere", "nouvelle_filiere_id"),
    ("ix_fk_demandechangementfiliere_traite_par_id", "demandechangementfiliere", "traite_par_id"),
    ("ix_fk_demandechangementfiliere_utilisateur_id", "demandechangementfiliere", "utilisateur_id"),
    ("ix_fk_demandechangementfiliere_nouvelle_faculte_id", "demandechangementfiliere", "nouvelle_faculte_id"),
    ("ix_fk_demandechangementfiliere_nouvelle_mention_id", "demandechangementfiliere", "nouvelle_mention_id"),
    ("ix_fk_devoir_cours_id", "devoir", "cours_id"),
    ("ix_fk_document_fiche_validee_par_id", "document", "fiche_validee_par_id"),
    ("ix_fk_document_filiere_id", "document", "filiere_id"),
    ("ix_fk_document_uploader_id", "document", "uploader_id"),
    ("ix_fk_evenementtableaublanc_utilisateur_id", "evenementtableaublanc", "utilisateur_id"),
    ("ix_fk_faq_cree_par_id", "faq", "cree_par_id"),
    ("ix_fk_filiere_faculte_id", "filiere", "faculte_id"),
    ("ix_fk_filiere_mention_id", "filiere", "mention_id"),
    ("ix_fk_inscriptioncours_utilisateur_id", "inscriptioncours", "utilisateur_id"),
    ("ix_fk_mention_domaine_id", "mention", "domaine_id"),
    ("ix_fk_notification_acteur_id", "notification", "acteur_id"),
    ("ix_fk_notification_cercle_id", "notification", "cercle_id"),
    ("ix_fk_notification_message_id", "notification", "message_id"),
    ("ix_fk_presenceseance_seance_id", "presenceseance", "seance_id"),
    ("ix_fk_presenceseance_utilisateur_id", "presenceseance", "utilisateur_id"),
    ("ix_fk_programmeuniversitaire_filiere_id", "programmeuniversitaire", "filiere_id"),
    ("ix_fk_referentielscolaire_valide_par_id", "referentielscolaire", "valide_par_id"),
    ("ix_fk_rendudevoir_utilisateur_id", "rendudevoir", "utilisateur_id"),
    ("ix_fk_reponsefeedback_admin_id", "reponsefeedback", "admin_id"),
    ("ix_fk_seance_cours_id", "seance", "cours_id"),
    ("ix_fk_sessiontuteur_utilisateur_id", "sessiontuteur", "utilisateur_id"),
    ("ix_fk_signalementquestionquiz_signale_par_id", "signalementquestionquiz", "signale_par_id"),
    ("ix_fk_signalementquestionquiz_tentative_id", "signalementquestionquiz", "tentative_id"),
    ("ix_fk_utilisateur_mention_id", "utilisateur", "mention_id"),
    ("ix_fk_utilisateur_universite_id", "utilisateur", "universite_id"),
    ("ix_fk_utilisateur_verification_enseignant_par_id", "utilisateur", "verification_enseignant_par_id"),
    ("ix_fk_utilisateur_filiere_id", "utilisateur", "filiere_id"),
)


def upgrade() -> None:
    for nom_index, table, colonne in _INDEXES:
        op.create_index(nom_index, table, [colonne])


def downgrade() -> None:
    for nom_index, table, _colonne in reversed(_INDEXES):
        op.drop_index(nom_index, table_name=table)
