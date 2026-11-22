"""Modèles du référentiel documentaire officiel EP/FRP.

Les fichiers originaux et les extractions sont privés. Une source importée
n'est jamais réputée officielle avant une validation administrative explicite.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, Column, Index, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


class ProgrammeOfficielScolaire(SQLModel, table=True):
    """Copie versionnée d'un document de programme importé par un admin."""

    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(unique=True, max_length=80)
    intitule: str = Field(max_length=250)
    organisme_emetteur: str = Field(max_length=180)
    type_document: str = Field(max_length=12, index=True)  # EP / FRP / AUTRE
    annee_publication: Optional[int] = Field(default=None, index=True)
    annee_scolaire: Optional[str] = Field(default=None, max_length=20, index=True)
    version_officielle: str = Field(default="", max_length=80)
    programme_matiere_id: int = Field(
        foreign_key="programmematierescolaire.id", index=True
    )
    source_url: Optional[str] = Field(default=None, max_length=1200)
    reference_source: str = Field(default="", max_length=1200)
    nom_fichier_original: str = Field(max_length=255)
    chemin_fichier: str = Field(max_length=1200)
    type_mime: str = Field(max_length=120)
    empreinte_sha256: str = Field(max_length=64)
    taille_octets: int
    texte_extrait: str = Field(default="", sa_column=Column(Text, nullable=False))
    statut_extraction: str = Field(default="en_attente", max_length=20, index=True)
    nombre_caracteres_extraits: int = Field(default=0)
    statut_validation: str = Field(default="a_verifier", max_length=20, index=True)
    motif_validation: str = Field(default="", max_length=4000)
    version_precedente_id: Optional[int] = Field(
        default=None,
        foreign_key="programmeofficielscolaire.id",
        index=True,
    )
    importe_par_id: int = Field(foreign_key="utilisateur.id", index=True)
    verifie_par_id: Optional[int] = Field(
        default=None, foreign_key="utilisateur.id", index=True
    )
    date_import: datetime = Field(default_factory=datetime.utcnow, index=True)
    date_verification: Optional[datetime] = None

    __table_args__ = (
        UniqueConstraint("empreinte_sha256", name="uq_programmeofficiel_empreinte_sha256"),
        CheckConstraint(
            "type_document IN ('EP', 'FRP', 'AUTRE')",
            name="ck_programmeofficiel_type_document",
        ),
        CheckConstraint(
            "statut_extraction IN ('en_attente', 'extrait', 'partiel', 'echec')",
            name="ck_programmeofficiel_statut_extraction",
        ),
        CheckConstraint(
            "statut_validation IN ('a_verifier', 'verifie', 'rejete', 'archive')",
            name="ck_programmeofficiel_statut_validation",
        ),
        CheckConstraint("taille_octets > 0", name="ck_programmeofficiel_taille"),
        Index(
            "ix_programmeofficiel_matiere_validation_date",
            "programme_matiere_id",
            "statut_validation",
            "date_import",
        ),
    )


class ElementProgrammeOfficiel(SQLModel, table=True):
    """Chapitre, leçon ou objectif proposé par extraction, puis relu par un admin."""

    id: Optional[int] = Field(default=None, primary_key=True)
    programme_id: int = Field(
        foreign_key="programmeofficielscolaire.id", index=True
    )
    parent_id: Optional[int] = Field(
        default=None,
        foreign_key="elementprogrammeofficiel.id",
        index=True,
    )
    lecon_referentielle_id: Optional[int] = Field(
        default=None, foreign_key="leconreferentielle.id", index=True
    )
    code: str = Field(max_length=60)
    type_element: str = Field(max_length=20, index=True)
    titre: str = Field(max_length=240)
    contenu: str = Field(default="", sa_column=Column(Text, nullable=False))
    ordre: int = Field(default=0)
    page_debut: Optional[int] = None
    statut_validation: str = Field(
        default="a_verifier", max_length=20, index=True
    )
    motif_validation: str = Field(default="", max_length=2000)
    valide_par_id: Optional[int] = Field(
        default=None, foreign_key="utilisateur.id", index=True
    )
    date_validation: Optional[datetime] = None
    date_creation: datetime = Field(default_factory=datetime.utcnow, index=True)

    __table_args__ = (
        UniqueConstraint(
            "programme_id", "code", name="uq_elementprogramme_programme_code"
        ),
        CheckConstraint(
            "type_element IN ('chapitre', 'lecon', 'rubrique', 'objectif')",
            name="ck_elementprogramme_type",
        ),
        CheckConstraint(
            "statut_validation IN ('a_verifier', 'verifie', 'rejete')",
            name="ck_elementprogramme_statut",
        ),
        Index(
            "ix_elementprogramme_programme_statut_ordre",
            "programme_id",
            "statut_validation",
            "ordre",
        ),
    )
