"""Ajoute les appartenances et le cloisonnement des cours par établissement."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "h1c7e9a2b4d6"
down_revision: Union[str, Sequence[str], None] = "g2a7f5d9c1e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("membre_etablissement"):
        op.create_table(
            "membre_etablissement",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("institution_id", sa.Integer(), sa.ForeignKey("etablissementpartenaire.id"), nullable=False),
            sa.Column("utilisateur_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=False),
            sa.Column("role", sa.String(24), nullable=False, server_default="etudiant"),
            sa.Column("est_actif", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("ajoute_par_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=True),
            sa.Column("date_creation", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
            sa.Column("date_maj", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
            sa.UniqueConstraint("institution_id", "utilisateur_id", name="uq_membre_etablissement_utilisateur"),
        )
    for name, columns in (
        ("ix_membre_etablissement_institution_id", ["institution_id"]),
        ("ix_membre_etablissement_utilisateur_id", ["utilisateur_id"]),
        ("ix_membre_etablissement_role", ["role"]),
        ("ix_membre_etablissement_est_actif", ["est_actif"]),
        ("ix_membre_etablissement_role_actif", ["institution_id", "role", "est_actif"]),
    ):
        indexes = {item["name"] for item in sa.inspect(bind).get_indexes("membre_etablissement")}
        if name not in indexes:
            op.create_index(name, "membre_etablissement", columns, unique=False)

    columns = {item["name"] for item in sa.inspect(bind).get_columns("cours")}
    if "institution_id" not in columns:
        if bind.dialect.name == "sqlite":
            # SQLite ne sait pas ajouter directement une FK par ALTER TABLE.
            # Alembic batch reconstruit la table en conservant ses contraintes.
            with op.batch_alter_table("cours", recreate="always") as batch:
                batch.add_column(
                    sa.Column("institution_id", sa.Integer(), nullable=True)
                )
                batch.create_foreign_key(
                    "fk_cours_institution_id_etablissementpartenaire",
                    "etablissementpartenaire",
                    ["institution_id"],
                    ["id"],
                )
        else:
            op.add_column(
                "cours",
                sa.Column("institution_id", sa.Integer(), nullable=True),
            )
            op.create_foreign_key(
                "fk_cours_institution_id_etablissementpartenaire",
                "cours",
                "etablissementpartenaire",
                ["institution_id"],
                ["id"],
            )
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("cours")}
    if "ix_cours_institution_id" not in indexes:
        op.create_index("ix_cours_institution_id", "cours", ["institution_id"], unique=False)

    # Reconstitue les appartenances des comptes déjà préinscrits.
    metadata = sa.MetaData()
    users = sa.Table("utilisateur", metadata, autoload_with=bind)
    members = sa.Table("membre_etablissement", metadata, autoload_with=bind)
    role_value = sa.cast(users.c.role, sa.String)
    role_expr = sa.case(
        (sa.func.lower(role_value) == "professeur", "professeur"),
        (sa.func.lower(role_value) == "admin", "responsable"),
        else_="etudiant",
    )
    selected = sa.select(
        users.c.institution_id,
        users.c.id,
        role_expr,
        sa.true(),
        sa.func.current_timestamp(),
        sa.func.current_timestamp(),
    ).where(users.c.institution_id.is_not(None))
    op.execute(
        sa.insert(members)
        .from_select(
            ["institution_id", "utilisateur_id", "role", "est_actif", "date_creation", "date_maj"],
            selected,
        )
        .prefix_with("OR IGNORE") if bind.dialect.name == "sqlite" else
        sa.insert(members)
        .from_select(
            ["institution_id", "utilisateur_id", "role", "est_actif", "date_creation", "date_maj"],
            selected.where(
                ~sa.exists(
                    sa.select(sa.literal(1)).select_from(members).where(
                        members.c.institution_id == users.c.institution_id,
                        members.c.utilisateur_id == users.c.id,
                    )
                )
            ),
        )
    )

    # Affecte les cours existants uniquement si le professeur a une appartenance
    # pédagogique active et un seul établissement connu : aucun rattachement
    # n'est deviné lorsque le périmètre est ambigu.
    op.execute(sa.text("""
        UPDATE cours AS c
        SET institution_id = u.institution_id
        FROM utilisateur AS u
        WHERE c.professeur_id = u.id
          AND c.institution_id IS NULL
          AND u.institution_id IS NOT NULL
          AND EXISTS (
              SELECT 1
              FROM membre_etablissement AS m
              WHERE m.utilisateur_id = u.id
                AND m.institution_id = u.institution_id
                AND m.est_actif = TRUE
                AND m.role IN ('professeur', 'responsable')
          )
          AND (
              SELECT COUNT(DISTINCT m2.institution_id)
              FROM membre_etablissement AS m2
              WHERE m2.utilisateur_id = u.id
                AND m2.est_actif = TRUE
          ) = 1
    """))


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("cours"):
        indexes = {item["name"] for item in sa.inspect(bind).get_indexes("cours")}
        if "ix_cours_institution_id" in indexes:
            op.drop_index("ix_cours_institution_id", table_name="cours")
        columns = {item["name"] for item in sa.inspect(bind).get_columns("cours")}
        if "institution_id" in columns:
            if bind.dialect.name == "sqlite":
                with op.batch_alter_table("cours", recreate="always") as batch:
                    foreign_keys = sa.inspect(bind).get_foreign_keys("cours")
                    for foreign_key in foreign_keys:
                        if foreign_key.get("constrained_columns") == ["institution_id"]:
                            batch.drop_constraint(foreign_key["name"], type_="foreignkey")
                    batch.drop_column("institution_id")
            else:
                op.drop_column("cours", "institution_id")
    if sa.inspect(bind).has_table("membre_etablissement"):
        indexes = {item["name"] for item in sa.inspect(bind).get_indexes("membre_etablissement")}
        for name in (
            "ix_membre_etablissement_role_actif",
            "ix_membre_etablissement_est_actif",
            "ix_membre_etablissement_role",
            "ix_membre_etablissement_utilisateur_id",
            "ix_membre_etablissement_institution_id",
        ):
            if name in indexes:
                op.drop_index(name, table_name="membre_etablissement")
        op.drop_table("membre_etablissement")
