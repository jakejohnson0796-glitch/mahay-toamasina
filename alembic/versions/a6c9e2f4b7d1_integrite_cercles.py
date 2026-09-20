"""renforcement de l'integrite des cercles et de la messagerie

Revision ID: a6c9e2f4b7d1
Revises: f7c2d9a4e1b6
Create Date: 2026-09-20 07:00:00.000000

Cette migration nettoie les doublons historiques AVANT d'ajouter les
contraintes/uniques qui manquaient aux modeles. Elle est volontairement
portable SQLite/PostgreSQL : le nettoyage des lignes se fait en Python a
partir de requetes SQL simples, puis les contraintes sont ajoutees avec les
outils Alembic.
"""
from collections import defaultdict
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a6c9e2f4b7d1"
down_revision: Union[str, None] = "f7c2d9a4e1b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _rows(conn, sql: str, **params):
    return list(conn.execute(sa.text(sql), params).mappings())


def _supprimer_ids(conn, table: str, ids: list[int]) -> None:
    if not ids:
        return
    conn.execute(
        sa.text(f"DELETE FROM {table} WHERE id IN :ids").bindparams(
            sa.bindparam("ids", expanding=True)
        ),
        {"ids": ids},
    )


def _nettoyer_membres(conn) -> None:
    # Repare d'abord l'invariant du createur : exactement une ligne membre
    # CREATEUR pour chaque CercleEtude. Les comptes admins/systeme sont
    # ensuite traites comme de simples membres admin par la logique applicative.
    cercles = _rows(conn, "SELECT id, createur_id FROM cercleetude")
    membres = _rows(
        conn,
        "SELECT id, cercle_id, utilisateur_id, role "
        "FROM membrecercle ORDER BY cercle_id, utilisateur_id, id"
    )

    par_cercle_utilisateur: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for membre in membres:
        par_cercle_utilisateur[(membre["cercle_id"], membre["utilisateur_id"])].append(membre)

    doublons = []
    a_garder = {}
    for cle, lignes in par_cercle_utilisateur.items():
        a_garder[cle] = lignes[0]
        doublons.extend(m["id"] for m in lignes[1:])

    # Un seul membre logique par (cercle, utilisateur).
    _supprimer_ids(conn, "membrecercle", doublons)

    # Le createur doit toujours etre membre et son role CREATEUR.
    for cercle in cercles:
        cercle_id = cercle["id"]
        createur_id = cercle["createur_id"]
        membre = a_garder.get((cercle_id, createur_id))
        if membre:
            conn.execute(
                sa.text("UPDATE membrecercle SET role = 'CREATEUR' WHERE id = :id"),
                {"id": membre["id"]},
            )
        else:
            conn.execute(
                sa.text(
                    "INSERT INTO membrecercle (cercle_id, utilisateur_id, role, date_adhesion) "
                    "VALUES (:cercle_id, :utilisateur_id, 'CREATEUR', CURRENT_TIMESTAMP)"
                ),
                {"cercle_id": cercle_id, "utilisateur_id": createur_id},
            )


def _nettoyer_reactions(conn) -> None:
    # Le code applicatif implemente une reaction unique par message et par
    # utilisateur. L'ancien schema n'imposait l'unicite que par type, donc
    # plusieurs emojis simultanes pouvaient exister. On conserve la ligne la
    # plus recente (id max), puis on resserre la contrainte.
    lignes = _rows(
        conn,
        "SELECT id, message_id, utilisateur_id "
        "FROM messagereaction ORDER BY message_id, utilisateur_id, id"
    )
    groupes: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for ligne in lignes:
        groupes[(ligne["message_id"], ligne["utilisateur_id"])].append(ligne)

    a_supprimer = []
    for _cle, lignes_groupe in groupes.items():
        if len(lignes_groupe) > 1:
            a_supprimer.extend(m["id"] for m in lignes_groupe[:-1])
    _supprimer_ids(conn, "messagereaction", a_supprimer)


def _nettoyer_signalements(conn) -> None:
    # Une seule plainte ouverte par (message, utilisateur). Apres traitement,
    # une nouvelle plainte reste possible.
    lignes = _rows(
        conn,
        "SELECT id, message_id, signale_par_id "
        "FROM signalementmessage "
        "WHERE traite = 0 "
        "ORDER BY message_id, signale_par_id, id"
    )
    groupes: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for ligne in lignes:
        groupes[(ligne["message_id"], ligne["signale_par_id"])].append(ligne)

    a_supprimer = []
    for _cle, lignes_groupe in groupes.items():
        a_supprimer.extend(m["id"] for m in lignes_groupe[1:])
    _supprimer_ids(conn, "signalementmessage", a_supprimer)


def _nettoyer_demandes_creation(conn) -> None:
    # Les demandes en attente sont uniques par identite du cercle national.
    # Deux variantes sont necessaires :
    #   - parcours : mention + filiere + niveau
    #   - tronc commun : mention + niveau, sans filiere
    lignes = _rows(
        conn,
        "SELECT id, mention_id, filiere_id, niveau "
        "FROM demandecreationcercle "
        "WHERE statut = 'EN_ATTENTE' "
        "ORDER BY id"
    )
    groupes: dict[tuple, list[dict]] = defaultdict(list)
    for ligne in lignes:
        if ligne["mention_id"] is None or ligne["niveau"] is None:
            continue
        cle = (
            "filiere",
            ligne["mention_id"],
            ligne["filiere_id"],
            ligne["niveau"],
        ) if ligne["filiere_id"] is not None else (
            "tronc",
            ligne["mention_id"],
            ligne["niveau"],
        )
        groupes[cle].append(ligne)

    for _cle, lignes_groupe in groupes.items():
        # On garde la plus ancienne demande, et on rejette les autres pour
        # ne jamais effacer l'historique d'une action utilisateur.
        for doublon in lignes_groupe[1:]:
            conn.execute(
                sa.text(
                    "UPDATE demandecreationcercle "
                    "SET statut = 'REJETEE', date_traitement = CURRENT_TIMESTAMP "
                    "WHERE id = :id"
                ),
                {"id": doublon["id"]},
            )


def upgrade() -> None:
    conn = op.get_bind()

    _nettoyer_membres(conn)
    _nettoyer_reactions(conn)
    _nettoyer_signalements(conn)
    _nettoyer_demandes_creation(conn)

    # Reactions : remplace l'ancienne unicite (message, utilisateur, type)
    # par le vrai invariant metier (message, utilisateur).
    with op.batch_alter_table("messagereaction") as batch_op:
        batch_op.drop_constraint(
            "uq_reaction_message_utilisateur_type",
            type_="unique",
        )
        batch_op.create_unique_constraint(
            "uq_reaction_message_utilisateur",
            ["message_id", "utilisateur_id"],
        )

    # Une seule appartenance logique dans un cercle.
    with op.batch_alter_table("membrecercle") as batch_op:
        batch_op.create_unique_constraint(
            "uq_membrecercle_cercle_utilisateur",
            ["cercle_id", "utilisateur_id"],
        )

    # Une seule demande de creation encore ouverte pour une identite de
    # cercle national. Les clauses partielles evitent de bloquer les lignes
    # deja traitees.
    op.create_index(
        "ix_demande_creation_unique_nationale_attente",
        "demandecreationcercle",
        ["mention_id", "filiere_id", "niveau"],
        unique=True,
        postgresql_where=sa.text(
            "statut = 'EN_ATTENTE' AND mention_id IS NOT NULL "
            "AND filiere_id IS NOT NULL AND niveau IS NOT NULL"
        ),
        sqlite_where=sa.text(
            "statut = 'EN_ATTENTE' AND mention_id IS NOT NULL "
            "AND filiere_id IS NOT NULL AND niveau IS NOT NULL"
        ),
    )
    op.create_index(
        "ix_demande_creation_unique_tronc_attente",
        "demandecreationcercle",
        ["mention_id", "niveau"],
        unique=True,
        postgresql_where=sa.text(
            "statut = 'EN_ATTENTE' AND mention_id IS NOT NULL "
            "AND filiere_id IS NULL AND niveau IS NOT NULL"
        ),
        sqlite_where=sa.text(
            "statut = 'EN_ATTENTE' AND mention_id IS NOT NULL "
            "AND filiere_id IS NULL AND niveau IS NOT NULL"
        ),
    )

    # Une seule plainte non traitee par membre et message.
    op.create_index(
        "ix_signalement_message_unique_nontraite",
        "signalementmessage",
        ["message_id", "signale_par_id"],
        unique=True,
        postgresql_where=sa.text("traite = false"),
        sqlite_where=sa.text("traite = 0"),
    )

    # Requetes frequentes du salon et de la file d'adhesion.
    op.create_index(
        "ix_messagecercle_cercle_date",
        "messagecercle",
        ["cercle_id", "date_envoi"],
    )
    op.create_index(
        "ix_demandeadhesion_cercle_statut_date",
        "demandeadhesioncercle",
        ["cercle_id", "statut", "date_creation"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_demandeadhesion_cercle_statut_date",
        table_name="demandeadhesioncercle",
    )
    op.drop_index(
        "ix_messagecercle_cercle_date",
        table_name="messagecercle",
    )
    op.drop_index(
        "ix_signalement_message_unique_nontraite",
        table_name="signalementmessage",
    )
    op.drop_index(
        "ix_demande_creation_unique_tronc_attente",
        table_name="demandecreationcercle",
    )
    op.drop_index(
        "ix_demande_creation_unique_nationale_attente",
        table_name="demandecreationcercle",
    )

    with op.batch_alter_table("membrecercle") as batch_op:
        batch_op.drop_constraint(
            "uq_membrecercle_cercle_utilisateur",
            type_="unique",
        )

    with op.batch_alter_table("messagereaction") as batch_op:
        batch_op.drop_constraint(
            "uq_reaction_message_utilisateur",
            type_="unique",
        )
        batch_op.create_unique_constraint(
            "uq_reaction_message_utilisateur_type",
            ["message_id", "utilisateur_id", "type_reaction"],
        )
