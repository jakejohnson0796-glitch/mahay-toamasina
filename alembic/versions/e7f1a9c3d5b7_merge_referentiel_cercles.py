"""Fusionne les deux branches Alembic du referentiel academique.

Revision ID: e7f1a9c3d5b7
Revises: 9d6a4c2e7f10, c2f4a8d1b7e6

La refonte des cercles et l'ajout de la composante dans les profils ont ete
developpes sur deux branches de migration issues du meme ancetre. Cette
migration de fusion est volontairement sans effet sur les donnees : elle
sert uniquement a donner a Alembic une tete unique pour que "upgrade head"
reste deterministe.
"""
from typing import Sequence, Union

from alembic import op  # noqa: F401


revision: str = "e7f1a9c3d5b7"
down_revision: Union[str, Sequence[str], None] = ("9d6a4c2e7f10", "c2f4a8d1b7e6")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
