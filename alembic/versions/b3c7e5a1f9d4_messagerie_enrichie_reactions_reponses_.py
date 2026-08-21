"""messagerie enrichie : reactions, reponses/thread, mentions, notifications

Revision ID: b3c7e5a1f9d4
Revises: e5b9c3f7a2d8
Create Date: 2026-08-20 20:30:00.000000

Premiere brique de la refonte de la messagerie des cercles (brief
"Messagerie des cercles + FAQ + Avis & Feedback") : ajoute uniquement les
modeles de donnees necessaires aux reactions emoji, aux reponses/threads,
aux mentions et a un systeme de notification generique reutilisable par
les futurs chantiers FAQ/Feedback. Aucune donnee existante n'est modifiee
ou supprimee ; toutes les nouvelles colonnes sur messagecercle sont
nullable ou ont un server_default pour rester compatibles avec les lignes
deja en production.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = 'b3c7e5a1f9d4'
down_revision: Union[str, None] = 'e5b9c3f7a2d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Messagerie enrichie sur messagecercle existant ---
    op.add_column('messagecercle', sa.Column('parent_message_id', sa.Integer(), nullable=True))
    op.add_column('messagecercle', sa.Column('date_modification', sa.DateTime(), nullable=True))
    op.add_column('messagecercle', sa.Column('epingle', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('messagecercle', sa.Column('epingle_par_id', sa.Integer(), nullable=True))
    op.add_column('messagecercle', sa.Column('date_epinglage', sa.DateTime(), nullable=True))
    with op.batch_alter_table('messagecercle') as batch_op:
        batch_op.create_foreign_key(
            'fk_messagecercle_parent_message_id', 'messagecercle', ['parent_message_id'], ['id']
        )
        batch_op.create_foreign_key(
            'fk_messagecercle_epingle_par_id', 'utilisateur', ['epingle_par_id'], ['id']
        )
    # Accelere le regroupement en thread ("6 reponses" -> COUNT WHERE
    # parent_message_id = X) et l'affichage du fil principal (parent NULL).
    op.create_index('ix_messagecercle_parent_message_id', 'messagecercle', ['parent_message_id'])

    # --- Reactions ---
    op.create_table(
        'messagereaction',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('message_id', sa.Integer(), nullable=False),
        sa.Column('utilisateur_id', sa.Integer(), nullable=False),
        sa.Column('type_reaction', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('date_creation', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['message_id'], ['messagecercle.id'], ),
        sa.ForeignKeyConstraint(['utilisateur_id'], ['utilisateur.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('message_id', 'utilisateur_id', 'type_reaction', name='uq_reaction_message_utilisateur_type'),
    )
    op.create_index('ix_messagereaction_message_id', 'messagereaction', ['message_id'])

    # --- Mentions ---
    op.create_table(
        'messagemention',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('message_id', sa.Integer(), nullable=False),
        sa.Column('utilisateur_mentionne_id', sa.Integer(), nullable=False),
        sa.Column('date_creation', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['message_id'], ['messagecercle.id'], ),
        sa.ForeignKeyConstraint(['utilisateur_mentionne_id'], ['utilisateur.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('message_id', 'utilisateur_mentionne_id', name='uq_mention_message_utilisateur'),
    )
    op.create_index('ix_messagemention_utilisateur_mentionne_id', 'messagemention', ['utilisateur_mentionne_id'])

    # --- Notifications (systeme generique, reutilisable par FAQ/Feedback) ---
    op.create_table(
        'notification',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('destinataire_id', sa.Integer(), nullable=False),
        sa.Column('type_notification', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('contenu', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('acteur_id', sa.Integer(), nullable=True),
        sa.Column('cercle_id', sa.Integer(), nullable=True),
        sa.Column('message_id', sa.Integer(), nullable=True),
        sa.Column('lu', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('date_creation', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['destinataire_id'], ['utilisateur.id'], ),
        sa.ForeignKeyConstraint(['acteur_id'], ['utilisateur.id'], ),
        sa.ForeignKeyConstraint(['cercle_id'], ['cercleetude.id'], ),
        sa.ForeignKeyConstraint(['message_id'], ['messagecercle.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    # Requete la plus frequente : "notifications non lues d'un
    # utilisateur, plus recentes d'abord" -> index compose.
    op.create_index('ix_notification_destinataire_date', 'notification', ['destinataire_id', 'date_creation'])
    op.create_index('ix_notification_destinataire_lu', 'notification', ['destinataire_id', 'lu'])


def downgrade() -> None:
    op.drop_index('ix_notification_destinataire_lu', table_name='notification')
    op.drop_index('ix_notification_destinataire_date', table_name='notification')
    op.drop_table('notification')

    op.drop_index('ix_messagemention_utilisateur_mentionne_id', table_name='messagemention')
    op.drop_table('messagemention')

    op.drop_index('ix_messagereaction_message_id', table_name='messagereaction')
    op.drop_table('messagereaction')

    op.drop_index('ix_messagecercle_parent_message_id', table_name='messagecercle')
    with op.batch_alter_table('messagecercle') as batch_op:
        batch_op.drop_constraint('fk_messagecercle_epingle_par_id', type_='foreignkey')
        batch_op.drop_constraint('fk_messagecercle_parent_message_id', type_='foreignkey')
    op.drop_column('messagecercle', 'date_epinglage')
    op.drop_column('messagecercle', 'epingle_par_id')
    op.drop_column('messagecercle', 'epingle')
    op.drop_column('messagecercle', 'date_modification')
    op.drop_column('messagecercle', 'parent_message_id')
