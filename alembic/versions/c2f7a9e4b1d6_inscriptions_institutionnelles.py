"""Ajoute les comptes institutionnels et l'identifiant de connexion étudiant."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c2f7a9e4b1d6"
down_revision: Union[str, Sequence[str], None] = "9f0b1c2d3e4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _colonnes(bind, table: str) -> set[str]:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table):
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("etablissementpartenaire"):
        op.create_table(
            "etablissementpartenaire",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("nom", sa.String(length=200), nullable=False),
            sa.Column("code", sa.String(length=32), nullable=False),
            sa.Column("type_etablissement", sa.String(length=30), nullable=False, server_default="universite"),
            sa.Column("region", sa.String(length=100), nullable=True),
            sa.Column("commune", sa.String(length=120), nullable=True),
            sa.Column("est_actif", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("cree_par_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=True),
            sa.Column("date_creation", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("code", name="uq_etablissementpartenaire_code"),
        )
        op.create_index("ix_etablissementpartenaire_nom", "etablissementpartenaire", ["nom"])
        op.create_index("ix_etablissementpartenaire_type_etablissement", "etablissementpartenaire", ["type_etablissement"])
        op.create_index("ix_etablissementpartenaire_est_actif", "etablissementpartenaire", ["est_actif"])

    colonnes = _colonnes(bind, "utilisateur")
    with op.batch_alter_table("utilisateur") as batch:
        if "identifiant_connexion" not in colonnes:
            batch.add_column(sa.Column("identifiant_connexion", sa.String(length=160), nullable=True))
        if "institution_id" not in colonnes:
            batch.add_column(sa.Column("institution_id", sa.Integer(), sa.ForeignKey("etablissementpartenaire.id"), nullable=True))
        if "matricule_institutionnel" not in colonnes:
            batch.add_column(sa.Column("matricule_institutionnel", sa.String(length=80), nullable=True))
        if "telephone" in colonnes:
            batch.alter_column("telephone", existing_type=sa.String(), nullable=True)

    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("utilisateur")}
    if "ix_utilisateur_identifiant_connexion" not in indexes:
        op.create_index("ix_utilisateur_identifiant_connexion", "utilisateur", ["identifiant_connexion"], unique=True)
    if "ix_utilisateur_institution_id" not in indexes:
        op.create_index("ix_utilisateur_institution_id", "utilisateur", ["institution_id"])
    if "ix_utilisateur_matricule_institutionnel" not in indexes:
        op.create_index("ix_utilisateur_matricule_institutionnel", "utilisateur", ["matricule_institutionnel"])
    if "uq_utilisateur_institution_matricule" not in indexes:
        op.create_index(
            "uq_utilisateur_institution_matricule", "utilisateur",
            ["institution_id", "matricule_institutionnel"], unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("utilisateur"):
        indexes = {item["name"] for item in sa.inspect(bind).get_indexes("utilisateur")}
        for name in (
            "uq_utilisateur_institution_matricule",
            "ix_utilisateur_matricule_institutionnel",
            "ix_utilisateur_institution_id",
            "ix_utilisateur_identifiant_connexion",
        ):
            if name in indexes:
                op.drop_index(name, table_name="utilisateur")
        colonnes = _colonnes(bind, "utilisateur")
        with op.batch_alter_table("utilisateur") as batch:
            for name in ("matricule_institutionnel", "institution_id", "identifiant_connexion"):
                if name in colonnes:
                    batch.drop_column(name)
    if sa.inspect(bind).has_table("etablissementpartenaire"):
        op.drop_table("etablissementpartenaire")
