"""Index de clés étrangères utilisés par les Cercles et le chat."""

from typing import Sequence, Union

from alembic import op


revision: str = "9a4f7d1c2e80"
down_revision: Union[str, None] = "8f3c9a2d7e41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_INDEXES = (
    ("ix_cercleetude_createur_id", "cercleetude", ["createur_id"]),
    ("ix_cercleetude_filiere_id", "cercleetude", ["filiere_id"]),
    ("ix_demandeadhesioncercle_traite_par_id", "demandeadhesioncercle", ["traite_par_id"]),
    ("ix_demandeadhesioncercle_utilisateur_id", "demandeadhesioncercle", ["utilisateur_id"]),
    ("ix_demandecreationcercle_cercle_cree_id", "demandecreationcercle", ["cercle_cree_id"]),
    ("ix_demandecreationcercle_filiere_id", "demandecreationcercle", ["filiere_id"]),
    ("ix_demandecreationcercle_traite_par_id", "demandecreationcercle", ["traite_par_id"]),
    ("ix_demandecreationcercle_utilisateur_id", "demandecreationcercle", ["utilisateur_id"]),
    ("ix_messagecercle_auteur_id", "messagecercle", ["auteur_id"]),
    ("ix_messagecercle_epingle_par_id", "messagecercle", ["epingle_par_id"]),
    ("ix_messagereaction_utilisateur_id", "messagereaction", ["utilisateur_id"]),
    ("ix_signalementmessage_signale_par_id", "signalementmessage", ["signale_par_id"]),
    ("ix_themedujour_cercle_id", "themedujour", ["cercle_id"]),
)


def upgrade() -> None:
    for nom_index, table, colonnes in _INDEXES:
        op.create_index(nom_index, table, colonnes)


def downgrade() -> None:
    for nom_index, table, _colonnes in reversed(_INDEXES):
        op.drop_index(nom_index, table_name=table)
