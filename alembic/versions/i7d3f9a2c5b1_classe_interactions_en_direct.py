"""Ajoute les sondages, groupes, documents partages et transcriptions consenties."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "i7d3f9a2c5b1"
down_revision: Union[str, Sequence[str], None] = "h4c9d1e7b2a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sondageseance",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("seance_id", sa.Integer(), sa.ForeignKey("seance.id"), nullable=False),
        sa.Column("cours_id", sa.Integer(), sa.ForeignKey("cours.id"), nullable=False),
        sa.Column("createur_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=False),
        sa.Column("question", sa.String(length=300), nullable=False),
        sa.Column("options_json", sa.String(length=2000), nullable=False),
        sa.Column("type_sondage", sa.String(length=12), nullable=False, server_default="sondage"),
        sa.Column("bonne_option", sa.Integer(), nullable=True),
        sa.Column("ouvert", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("date_creation", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("date_cloture", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_sondage_seance", "sondageseance", ["seance_id"])
    op.create_index("ix_sondage_cours", "sondageseance", ["cours_id"])
    op.create_index("ix_sondage_ouvert", "sondageseance", ["ouvert"])

    op.create_table(
        "reponsesondageseance",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("sondage_id", sa.Integer(), sa.ForeignKey("sondageseance.id"), nullable=False),
        sa.Column("utilisateur_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=False),
        sa.Column("option_index", sa.Integer(), nullable=False),
        sa.Column("date_creation", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("sondage_id", "utilisateur_id", name="uq_reponse_sondage_utilisateur"),
    )
    op.create_index("ix_reponse_sondage", "reponsesondageseance", ["sondage_id"])
    op.create_index("ix_reponse_utilisateur", "reponsesondageseance", ["utilisateur_id"])

    op.create_table(
        "groupesoussalle",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("seance_id", sa.Integer(), sa.ForeignKey("seance.id"), nullable=False),
        sa.Column("nom", sa.String(length=80), nullable=False),
        sa.Column("nom_salle_livekit", sa.String(length=180), nullable=False, unique=True),
        sa.Column("date_creation", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_groupe_sous_salle_seance", "groupesoussalle", ["seance_id"])

    op.create_table(
        "affectationsoussalle",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("seance_id", sa.Integer(), sa.ForeignKey("seance.id"), nullable=False),
        sa.Column("groupe_id", sa.Integer(), sa.ForeignKey("groupesoussalle.id"), nullable=False),
        sa.Column("utilisateur_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=False),
        sa.Column("date_creation", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("seance_id", "utilisateur_id", name="uq_affectation_sous_salle_utilisateur"),
    )
    op.create_index("ix_affectation_sous_salle_seance", "affectationsoussalle", ["seance_id"])
    op.create_index("ix_affectation_sous_salle_groupe", "affectationsoussalle", ["groupe_id"])
    op.create_index("ix_affectation_sous_salle_utilisateur", "affectationsoussalle", ["utilisateur_id"])

    op.create_table(
        "documentpartageseance",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("seance_id", sa.Integer(), sa.ForeignKey("seance.id"), nullable=False),
        sa.Column("cours_id", sa.Integer(), sa.ForeignKey("cours.id"), nullable=False),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("document.id"), nullable=False),
        sa.Column("partage_par_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=False),
        sa.Column("date_creation", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("seance_id", "document_id", name="uq_document_partage_seance"),
    )
    op.create_index("ix_document_partage_seance", "documentpartageseance", ["seance_id"])
    op.create_index("ix_document_partage_cours", "documentpartageseance", ["cours_id"])
    op.create_index("ix_document_partage_document", "documentpartageseance", ["document_id"])

    op.create_table(
        "consentementtranscription",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("seance_id", sa.Integer(), sa.ForeignKey("seance.id"), nullable=False),
        sa.Column("utilisateur_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=False),
        sa.Column("consenti", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("date_creation", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("date_modification", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("seance_id", "utilisateur_id", name="uq_consentement_transcription_utilisateur"),
    )
    op.create_index("ix_consentement_transcription_seance", "consentementtranscription", ["seance_id"])
    op.create_index("ix_consentement_transcription_utilisateur", "consentementtranscription", ["utilisateur_id"])

    op.create_table(
        "transcriptionseance",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("seance_id", sa.Integer(), sa.ForeignKey("seance.id"), nullable=False, unique=True),
        sa.Column("demarree_par_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=False),
        sa.Column("agent_dispatch_id", sa.String(length=120), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("contenu", sa.String(length=100000), nullable=False, server_default=""),
        sa.Column("resume_ia", sa.String(length=30000), nullable=False, server_default=""),
        sa.Column("date_debut", sa.DateTime(), nullable=True),
        sa.Column("date_fin", sa.DateTime(), nullable=True),
        sa.Column("date_modification", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_transcription_seance_id", "transcriptionseance", ["seance_id"])
    op.create_index("ix_transcription_active", "transcriptionseance", ["active"])

    # Ces tables sont accessibles uniquement via le backend authentifie.
    # Aucune lecture/ecriture directe via la Supabase Data API n'est necessaire.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        tables = (
            "sondageseance",
            "reponsesondageseance",
            "groupesoussalle",
            "affectationsoussalle",
            "documentpartageseance",
            "consentementtranscription",
            "transcriptionseance",
        )
        roles = bind.execute(
            sa.text("SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')")
        ).scalars().all()
        quote = bind.dialect.identifier_preparer.quote
        for table in tables:
            bind.exec_driver_sql(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
            bind.exec_driver_sql(f"REVOKE ALL PRIVILEGES ON TABLE public.{table} FROM PUBLIC")
            for role in roles:
                if role in {"anon", "authenticated"}:
                    bind.exec_driver_sql(
                        f"REVOKE ALL PRIVILEGES ON TABLE public.{table} FROM " + quote(role)
                    )


def downgrade() -> None:
    op.drop_index("ix_transcription_active", table_name="transcriptionseance")
    op.drop_index("ix_transcription_seance_id", table_name="transcriptionseance")
    op.drop_table("transcriptionseance")

    op.drop_index("ix_consentement_transcription_utilisateur", table_name="consentementtranscription")
    op.drop_index("ix_consentement_transcription_seance", table_name="consentementtranscription")
    op.drop_table("consentementtranscription")

    op.drop_index("ix_document_partage_document", table_name="documentpartageseance")
    op.drop_index("ix_document_partage_cours", table_name="documentpartageseance")
    op.drop_index("ix_document_partage_seance", table_name="documentpartageseance")
    op.drop_table("documentpartageseance")

    op.drop_index("ix_affectation_sous_salle_utilisateur", table_name="affectationsoussalle")
    op.drop_index("ix_affectation_sous_salle_groupe", table_name="affectationsoussalle")
    op.drop_index("ix_affectation_sous_salle_seance", table_name="affectationsoussalle")
    op.drop_table("affectationsoussalle")

    op.drop_index("ix_groupe_sous_salle_seance", table_name="groupesoussalle")
    op.drop_table("groupesoussalle")

    op.drop_index("ix_reponse_utilisateur", table_name="reponsesondageseance")
    op.drop_index("ix_reponse_sondage", table_name="reponsesondageseance")
    op.drop_table("reponsesondageseance")

    op.drop_index("ix_sondage_ouvert", table_name="sondageseance")
    op.drop_index("ix_sondage_cours", table_name="sondageseance")
    op.drop_index("ix_sondage_seance", table_name="sondageseance")
    op.drop_table("sondageseance")
