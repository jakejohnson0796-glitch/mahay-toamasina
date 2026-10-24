"""Normalise les cycles déclarés par les professeurs.

Revision ID: d8f41b2c6e90
Revises: c5f7a12e9b31
"""
from alembic import op
import sqlalchemy as sa

revision = "d8f41b2c6e90"
down_revision = "c5f7a12e9b31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cycleenseigne",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "utilisateur_id",
            sa.Integer(),
            sa.ForeignKey("utilisateur.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cycle_education", sa.String(length=20), nullable=False),
        sa.Column(
            "date_declaration",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "cycle_education IN ('college', 'lycee', 'universite')",
            name="ck_cycleenseigne_cycle",
        ),
        sa.UniqueConstraint(
            "utilisateur_id",
            "cycle_education",
            name="uq_cycleenseigne_utilisateur_cycle",
        ),
    )
    op.create_index(
        "ix_cycleenseigne_utilisateur_id",
        "cycleenseigne",
        ["utilisateur_id"],
    )
    op.create_index(
        "ix_cycleenseigne_cycle_education",
        "cycleenseigne",
        ["cycle_education"],
    )
    # Reprendre le cycle principal déclaré par les profils enseignants déjà
    # présents sans modifier leur rôle, leur décision administrative ou leur
    # parcours universitaire/scolaire existant.
    op.execute(sa.text(
        "INSERT INTO cycleenseigne (utilisateur_id, cycle_education, date_declaration) "
        "SELECT u.id, u.cycle_education, CURRENT_TIMESTAMP "
        "FROM utilisateur AS u "
        "WHERE u.profil_souhaite = 'professeur' "
        "AND u.cycle_education IN ('college', 'lycee', 'universite') "
        "AND NOT EXISTS ("
        "SELECT 1 FROM cycleenseigne AS c "
        "WHERE c.utilisateur_id = u.id AND c.cycle_education = u.cycle_education"
        ")"
    ))


def downgrade() -> None:
    op.drop_index("ix_cycleenseigne_cycle_education", table_name="cycleenseigne")
    op.drop_index("ix_cycleenseigne_utilisateur_id", table_name="cycleenseigne")
    op.drop_table("cycleenseigne")
