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

    # Pont idempotent vers le catalogue universitaire canonique.
    # Les lignes et leurs codes UNIV-* sont des références techniques,
    # pas une seconde copie des facultés/programmes.
    if bind.dialect.name == "postgresql":
        op.add_column(
            "etablissementpartenaire",
            sa.Column("universite_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_etablissementpartenaire_universite_id_universite",
            "etablissementpartenaire",
            "universite",
            ["universite_id"],
            ["id"],
        )
        op.create_unique_constraint(
            "uq_etablissementpartenaire_universite_id",
            "etablissementpartenaire",
            ["universite_id"],
        )
        op.execute(sa.text("""
            INSERT INTO etablissementpartenaire
                (nom, code, type_etablissement, commune, est_actif, universite_id)
            SELECT u.nom, 'UNIV-' || u.id::text, 'universite', u.ville, u.est_active, u.id
            FROM universite AS u
            WHERE NOT EXISTS (
                SELECT 1 FROM etablissementpartenaire ep
                WHERE ep.universite_id = u.id
            )
            ON CONFLICT DO NOTHING
        """))
        # Le rattachement confirmé concerne le compte administrateur
        # de l'Université de Toamasina (universite.id = 1).
        op.execute(sa.text("""
            UPDATE utilisateur AS u
            SET institution_id = ep.id
            FROM etablissementpartenaire AS ep
            WHERE ep.universite_id = 1
              AND u.role::text = 'admin'
              AND u.universite_id = 1
              AND u.institution_id IS NULL
        """))
    else:
        # SQLite : colonne/FK/unique sont gérés par Alembic batch.
        with op.batch_alter_table("etablissementpartenaire") as batch:
            batch.add_column(sa.Column("universite_id", sa.Integer(), nullable=True))
            batch.create_foreign_key(
                "fk_etablissementpartenaire_universite_id_universite",
                "universite",
                ["universite_id"],
                ["id"],
            )
            batch.create_unique_constraint(
                "uq_etablissementpartenaire_universite_id", ["universite_id"]
            )
        bind.execute(sa.text("""
            INSERT INTO etablissementpartenaire
                (nom, code, type_etablissement, commune, est_actif, universite_id)
            SELECT u.nom, 'UNIV-' || CAST(u.id AS TEXT), 'universite', u.ville, u.est_active, u.id
            FROM universite AS u
            WHERE NOT EXISTS (
                SELECT 1 FROM etablissementpartenaire ep
                WHERE ep.universite_id = u.id
            )
        """))
        bind.execute(sa.text("""
            UPDATE utilisateur
            SET institution_id = (
                SELECT ep.id FROM etablissementpartenaire ep
                WHERE ep.universite_id = 1
            )
            WHERE lower(CAST(role AS TEXT)) = 'admin'
              AND universite_id = 1
              AND institution_id IS NULL
        """))

    # Même posture que les autres tables du schéma Supabase public.
    # L'application serveur se connecte avec un rôle backend BYPASSRLS ;
    # l'activation empêche toute exposition accidentelle via la Data API.
    # SQLite n'implémente pas RLS ; le contrôle est appliqué sur PostgreSQL.
    if bind.dialect.name == "postgresql":
        op.execute(sa.text(
            "ALTER TABLE membre_etablissement ENABLE ROW LEVEL SECURITY"
        ))
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

    course_columns = {
        item["name"] for item in sa.inspect(bind).get_columns("cours")
    }
    if "affectation_institutionnelle_requise" not in course_columns:
        op.add_column(
            "cours",
            sa.Column(
                "affectation_institutionnelle_requise",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
    course_indexes = {
        item["name"] for item in sa.inspect(bind).get_indexes("cours")
    }
    if "ix_cours_affectation_institutionnelle_requise" not in course_indexes:
        op.create_index(
            "ix_cours_affectation_institutionnelle_requise",
            "cours",
            ["affectation_institutionnelle_requise"],
            unique=False,
        )

    # Rattache les notifications pédagogiques à leur cours pour contrôler
    # les anciennes alertes lorsqu'une inscription ou une appartenance expire.
    notification_columns = {
        item["name"] for item in sa.inspect(bind).get_columns("notification")
    }
    if "cours_id" not in notification_columns:
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("notification", recreate="always") as batch:
                batch.add_column(sa.Column("cours_id", sa.Integer(), nullable=True))
                batch.create_foreign_key(
                    "fk_notification_cours_id_cours",
                    "cours",
                    ["cours_id"],
                    ["id"],
                    ondelete="SET NULL",
                )
        else:
            op.add_column(
                "notification",
                sa.Column("cours_id", sa.Integer(), nullable=True),
            )
            op.create_foreign_key(
                "fk_notification_cours_id_cours",
                "notification",
                "cours",
                ["cours_id"],
                ["id"],
                ondelete="SET NULL",
            )
    notification_indexes = {
        item["name"] for item in sa.inspect(bind).get_indexes("notification")
    }
    if "ix_notification_cours_id" not in notification_indexes:
        op.create_index(
            "ix_notification_cours_id", "notification", ["cours_id"], unique=False
        )

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
    ).where(
        users.c.institution_id.is_not(None),
        sa.func.lower(role_value).in_(("professeur", "admin", "etudiant")),
    )
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

    # Un cours est automatiquement rattaché uniquement si son professeur
    # détient exactement une appartenance pédagogique active. Une situation
    # multiétablissement est mise en quarantaine jusqu'à arbitrage admin.
    op.execute(sa.text("""
        UPDATE cours
        SET institution_id = (
            SELECT MIN(m.institution_id)
            FROM membre_etablissement AS m
            JOIN etablissementpartenaire AS ep
              ON ep.id = m.institution_id
            WHERE m.utilisateur_id = cours.professeur_id
              AND m.est_actif = TRUE
              AND ep.est_actif = TRUE
              AND m.role IN ('professeur', 'responsable')
            GROUP BY m.utilisateur_id
            HAVING COUNT(DISTINCT m.institution_id) = 1
        )
        WHERE institution_id IS NULL
          AND (
              SELECT COUNT(DISTINCT m.institution_id)
              FROM membre_etablissement AS m
              JOIN etablissementpartenaire AS ep
                ON ep.id = m.institution_id
              WHERE m.utilisateur_id = cours.professeur_id
                AND m.est_actif = TRUE
                AND ep.est_actif = TRUE
                AND m.role IN ('professeur', 'responsable')
          ) = 1
    """))
    op.execute(sa.text("""
        UPDATE cours
        SET affectation_institutionnelle_requise = TRUE
        WHERE institution_id IS NULL
          AND EXISTS (
              SELECT 1
              FROM membre_etablissement AS m
              WHERE m.utilisateur_id = cours.professeur_id
                AND m.role IN ('professeur', 'responsable')
          )
    """))


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("notification"):
        notification_indexes = {
            item["name"] for item in sa.inspect(bind).get_indexes("notification")
        }
        if "ix_notification_cours_id" in notification_indexes:
            op.drop_index("ix_notification_cours_id", table_name="notification")
        notification_columns = {
            item["name"] for item in sa.inspect(bind).get_columns("notification")
        }
        if "cours_id" in notification_columns:
            if bind.dialect.name == "sqlite":
                with op.batch_alter_table("notification", recreate="always") as batch:
                    for foreign_key in sa.inspect(bind).get_foreign_keys("notification"):
                        if foreign_key.get("constrained_columns") == ["cours_id"]:
                            batch.drop_constraint(
                                foreign_key["name"], type_="foreignkey"
                            )
                    batch.drop_column("cours_id")
            else:
                op.drop_constraint(
                    "fk_notification_cours_id_cours",
                    "notification",
                    type_="foreignkey",
                )
                op.drop_column("notification", "cours_id")

    if sa.inspect(bind).has_table("cours"):
        indexes = {item["name"] for item in sa.inspect(bind).get_indexes("cours")}
        if "ix_cours_institution_id" in indexes:
            op.drop_index("ix_cours_institution_id", table_name="cours")
        if "ix_cours_affectation_institutionnelle_requise" in indexes:
            op.drop_index(
                "ix_cours_affectation_institutionnelle_requise",
                table_name="cours",
            )
        columns = {item["name"] for item in sa.inspect(bind).get_columns("cours")}
        if bind.dialect.name == "sqlite":
            if "institution_id" in columns or "affectation_institutionnelle_requise" in columns:
                with op.batch_alter_table("cours", recreate="always") as batch:
                    foreign_keys = sa.inspect(bind).get_foreign_keys("cours")
                    for foreign_key in foreign_keys:
                        if foreign_key.get("constrained_columns") == ["institution_id"] and foreign_key.get("name"):
                            batch.drop_constraint(foreign_key["name"], type_="foreignkey")
                    if "affectation_institutionnelle_requise" in columns:
                        batch.drop_column("affectation_institutionnelle_requise")
                    if "institution_id" in columns:
                        batch.drop_column("institution_id")
        else:
            if "affectation_institutionnelle_requise" in columns:
                op.drop_column("cours", "affectation_institutionnelle_requise")
            if "institution_id" in columns:
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
