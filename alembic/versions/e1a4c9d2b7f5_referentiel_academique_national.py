"""referentiel academique national (universite, mention, programme)

Revision ID: e1a4c9d2b7f5
Revises: 6a1c8e4b7f30
Create Date: 2026-08-15 12:00:00.000000

IMPORTANT (voir analyse presentee a Jake avant cette migration) :
aucun ID existant de Faculte/Filiere n'est renumerote. Cette migration
est purement additive : nouvelles tables + nouvelles colonnes nullables
(sauf ou un server_default permet de rester NOT NULL sans casser les
lignes existantes). Les donnees de Toamasina deja en base sont
rattachees a une premiere "Universite de Toamasina" creee ici — fait
deja vrai (ces filieres sont deja celles de cette universite), aucune
invention de donnees.

Les enums (str, Enum) du projet stockent le NOM du membre Python en
MAJUSCULES en base (ex: "ACTIF", pas "actif") — voir la migration
c4e91a2f7b6d pour la meme remarque deja documentee. Le SQL de backfill
ci-dessous respecte cette convention.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = 'e1a4c9d2b7f5'
down_revision: Union[str, None] = '6a1c8e4b7f30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Nouvelles tables du referentiel ---
    op.create_table(
        'universite',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nom', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('ville', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('code', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('est_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_universite_nom'), 'universite', ['nom'], unique=True)
    op.create_index(op.f('ix_universite_code'), 'universite', ['code'], unique=True)

    op.create_table(
        'mention',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nom', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('est_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_mention_nom'), 'mention', ['nom'], unique=True)

    # --- Faculte -> Universite ---
    with op.batch_alter_table('faculte') as batch_op:
        batch_op.add_column(sa.Column('universite_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_faculte_universite', 'universite', ['universite_id'], ['id'])

    # --- Filiere -> Mention (nullable, non affecte automatiquement) ---
    with op.batch_alter_table('filiere') as batch_op:
        batch_op.add_column(sa.Column('mention_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_filiere_mention', 'mention', ['mention_id'], ['id'])

    op.create_table(
        'programmeuniversitaire',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('universite_id', sa.Integer(), nullable=False),
        sa.Column('filiere_id', sa.Integer(), nullable=False),
        sa.Column('annee_academique', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('est_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(['universite_id'], ['universite.id']),
        sa.ForeignKeyConstraint(['filiere_id'], ['filiere.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_programme_universite_filiere', 'programmeuniversitaire', ['universite_id', 'filiere_id'])

    # --- Utilisateur : universite_id + niveau (nullables, comptes existants inchanges) ---
    with op.batch_alter_table('utilisateur') as batch_op:
        batch_op.add_column(sa.Column('universite_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_utilisateur_universite', 'universite', ['universite_id'], ['id'])
        batch_op.add_column(sa.Column('niveau', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column('niveau_modifie_le', sa.DateTime(), nullable=True))

    # --- CercleEtude : mention_id + niveau (nullables) + statut (NOT NULL, defaut ACTIF) ---
    # mention_id est denormalise a dessein : un cercle national est
    # identifie par (mention_id, filiere_id, niveau), pas par universite
    # (voir §17 et §27 de la mise a jour "cercles nationaux").
    with op.batch_alter_table('cercleetude') as batch_op:
        batch_op.add_column(sa.Column('mention_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_cercleetude_mention', 'mention', ['mention_id'], ['id'])
        batch_op.add_column(sa.Column('niveau', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column('statut', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='ACTIF'))

    # Index unique PARTIEL : un seul cercle ACTIF par (mention_id,
    # filiere_id, niveau) — mais UNIQUEMENT quand les 3 sont renseignes.
    # Les cercles "libres" (l'un des 3 = NULL) restent illimites, comme
    # avant cette evolution (voir §17-19 de la mise a jour "cercles
    # nationaux" + decision prise avec Jake : ne pas forcer une
    # migration retroactive des cercles existants). Meme remarque que
    # c4e91a2f7b6d sur le nom du membre Enum en MAJUSCULES en base.
    op.create_index(
        'ix_cercle_national_unique_actif',
        'cercleetude',
        ['mention_id', 'filiere_id', 'niveau'],
        unique=True,
        postgresql_where=sa.text("statut = 'ACTIF' AND mention_id IS NOT NULL AND filiere_id IS NOT NULL AND niveau IS NOT NULL"),
        sqlite_where=sa.text("statut = 'ACTIF' AND mention_id IS NOT NULL AND filiere_id IS NOT NULL AND niveau IS NOT NULL"),
    )

    # --- MembreCercle : role (NOT NULL, defaut MEMBRE puis backfill CREATEUR) ---
    with op.batch_alter_table('membrecercle') as batch_op:
        batch_op.add_column(sa.Column('role', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='MEMBRE'))

    # --- DemandeAdhesionCercle : raison (nullable — les demandes existantes n'en ont pas) ---
    with op.batch_alter_table('demandeadhesioncercle') as batch_op:
        batch_op.add_column(sa.Column('raison', sqlmodel.sql.sqltypes.AutoString(), nullable=True))

    # --- Nouvelles tables de workflow (§24-26 et §17 du brief, pas encore branchees a l'UI) ---
    op.create_table(
        'demandecreationcercle',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('utilisateur_id', sa.Integer(), nullable=False),
        sa.Column('mention_id', sa.Integer(), nullable=True),
        sa.Column('filiere_id', sa.Integer(), nullable=True),
        sa.Column('niveau', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('nom', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('raison', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('statut', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('date_creation', sa.DateTime(), nullable=False),
        sa.Column('date_traitement', sa.DateTime(), nullable=True),
        sa.Column('traite_par_id', sa.Integer(), nullable=True),
        sa.Column('cercle_cree_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['utilisateur_id'], ['utilisateur.id']),
        sa.ForeignKeyConstraint(['mention_id'], ['mention.id']),
        sa.ForeignKeyConstraint(['filiere_id'], ['filiere.id']),
        sa.ForeignKeyConstraint(['traite_par_id'], ['utilisateur.id']),
        sa.ForeignKeyConstraint(['cercle_cree_id'], ['cercleetude.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'demandechangementfiliere',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('utilisateur_id', sa.Integer(), nullable=False),
        sa.Column('ancienne_filiere_id', sa.Integer(), nullable=True),
        sa.Column('nouvelle_filiere_id', sa.Integer(), nullable=False),
        sa.Column('motif', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('statut', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('date_creation', sa.DateTime(), nullable=False),
        sa.Column('date_traitement', sa.DateTime(), nullable=True),
        sa.Column('traite_par_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['utilisateur_id'], ['utilisateur.id']),
        sa.ForeignKeyConstraint(['ancienne_filiere_id'], ['filiere.id']),
        sa.ForeignKeyConstraint(['nouvelle_filiere_id'], ['filiere.id']),
        sa.ForeignKeyConstraint(['traite_par_id'], ['utilisateur.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # ================================================================
    # BACKFILL DE DONNEES REELLES (rien d'invente, voir la docstring
    # en tete de fichier)
    # ================================================================
    connexion = op.get_bind()

    # 1) Universite de Toamasina : seule universite connue a ce jour.
    connexion.execute(sa.text(
        "INSERT INTO universite (nom, ville, code, est_active) "
        "VALUES ('Universite de Toamasina', 'Toamasina', 'UTOAMASINA', TRUE)"
    ))
    universite_toamasina_id = connexion.execute(
        sa.text("SELECT id FROM universite WHERE nom = 'Universite de Toamasina'")
    ).scalar()

    # 2) Toutes les Faculte existantes sont, dans les faits, deja des
    #    facultes de l'Universite de Toamasina (seule universite geree
    #    par Mahay jusqu'ici) : rattachement direct, aucune ambiguite.
    connexion.execute(
        sa.text("UPDATE faculte SET universite_id = :uid WHERE universite_id IS NULL")
        .bindparams(uid=universite_toamasina_id)
    )

    # 3) Chaque Filiere existante est deja, de fait, proposee a
    #    l'Universite de Toamasina : creer la ligne de liaison
    #    correspondante (fait vrai, pas une supposition).
    filiere_ids = [row[0] for row in connexion.execute(sa.text("SELECT id FROM filiere"))]
    for filiere_id in filiere_ids:
        connexion.execute(
            sa.text(
                "INSERT INTO programmeuniversitaire (universite_id, filiere_id, est_active) "
                "VALUES (:uid, :fid, TRUE)"
            ).bindparams(uid=universite_toamasina_id, fid=filiere_id)
        )

    # 4) role sur MembreCercle : le createur du cercle (CercleEtude.createur_id)
    #    doit avoir role=CREATEUR sur sa propre ligne de membre, pas le
    #    defaut MEMBRE pose ci-dessus pour toutes les lignes existantes.
    connexion.execute(sa.text(
        "UPDATE membrecercle SET role = 'CREATEUR' "
        "WHERE (cercle_id, utilisateur_id) IN ("
        "  SELECT id, createur_id FROM cercleetude"
        ")"
    ))

    # --- Maintenant que toutes les Faculte ont un universite_id, on
    #     peut resserrer la contrainte (aucune ligne ne violera NOT NULL). ---
    with op.batch_alter_table('faculte') as batch_op:
        batch_op.alter_column('universite_id', nullable=False)


def downgrade() -> None:
    with op.batch_alter_table('faculte') as batch_op:
        batch_op.alter_column('universite_id', nullable=True)

    op.drop_table('demandechangementfiliere')
    op.drop_table('demandecreationcercle')

    with op.batch_alter_table('demandeadhesioncercle') as batch_op:
        batch_op.drop_column('raison')
    with op.batch_alter_table('membrecercle') as batch_op:
        batch_op.drop_column('role')
    op.drop_index('ix_cercle_national_unique_actif', table_name='cercleetude')
    with op.batch_alter_table('cercleetude') as batch_op:
        batch_op.drop_column('statut')
        batch_op.drop_column('niveau')
        batch_op.drop_constraint('fk_cercleetude_mention', type_='foreignkey')
        batch_op.drop_column('mention_id')
    with op.batch_alter_table('utilisateur') as batch_op:
        batch_op.drop_constraint('fk_utilisateur_universite', type_='foreignkey')
        batch_op.drop_column('niveau_modifie_le')
        batch_op.drop_column('niveau')
        batch_op.drop_column('universite_id')

    op.drop_index('ix_programme_universite_filiere', table_name='programmeuniversitaire')
    op.drop_table('programmeuniversitaire')

    with op.batch_alter_table('filiere') as batch_op:
        batch_op.drop_constraint('fk_filiere_mention', type_='foreignkey')
        batch_op.drop_column('mention_id')
    with op.batch_alter_table('faculte') as batch_op:
        batch_op.drop_constraint('fk_faculte_universite', type_='foreignkey')
        batch_op.drop_column('universite_id')

    op.drop_index(op.f('ix_mention_nom'), table_name='mention')
    op.drop_table('mention')
    op.drop_index(op.f('ix_universite_code'), table_name='universite')
    op.drop_index(op.f('ix_universite_nom'), table_name='universite')
    op.drop_table('universite')
