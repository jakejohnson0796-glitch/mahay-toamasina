"""
Modeles de donnees de MAHAY Toamasina.

SQLModel = SQLAlchemy + Pydantic en un seul objet : chaque classe ci-dessous
est a la fois une table SQLite ET un schema de validation. C'est ce qui
permet de rester 100% Python sans dupliquer les definitions.
"""
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import SQLModel, Field, Relationship


class RoleUtilisateur(str, Enum):
    ETUDIANT = "etudiant"
    SPONSOR = "sponsor"      # repetiteur, petit commerce, service pour etudiants
    ADMIN = "admin"


class TypeDocument(str, Enum):
    ANNALE = "annale"        # sujet d'examen/partiel des annees precedentes
    CORRIGE = "corrige"      # corrige d'une annale
    FICHE = "fiche"          # fiche de revision
    COURS = "cours"          # support de cours complet


class StatutDocument(str, Enum):
    EN_ATTENTE = "en_attente"   # vient d'etre depose, pas encore visible publiquement
    APPROUVE = "approuve"       # valide par un moderateur, visible dans le manifeste
    REJETE = "rejete"


class StatutAbonnement(str, Enum):
    EN_ATTENTE_PAIEMENT = "en_attente_paiement"
    ACTIF = "actif"
    EXPIRE = "expire"


class Faculte(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    nom: str = Field(index=True, unique=True)

    filieres: list["Filiere"] = Relationship(back_populates="faculte")


class Filiere(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    nom: str
    faculte_id: int = Field(foreign_key="faculte.id")

    faculte: Optional[Faculte] = Relationship(back_populates="filieres")


class Utilisateur(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    nom: str
    # Le telephone sert d'identifiant de connexion : c'est ce que tout le
    # monde utilise deja pour mobile money, plus fiable qu'un email ici.
    telephone: str = Field(index=True, unique=True)
    mot_de_passe_hash: str
    role: RoleUtilisateur = Field(default=RoleUtilisateur.ETUDIANT)
    filiere_id: Optional[int] = Field(default=None, foreign_key="filiere.id")
    date_creation: datetime = Field(default_factory=datetime.utcnow)


class Document(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    # Reference style "manifeste de cargo portuaire" : TOA-DEG-2024-0147
    reference: str = Field(index=True, unique=True)
    titre: str
    matiere: str
    type_document: TypeDocument
    annee: int
    filiere_id: int = Field(foreign_key="filiere.id")
    uploader_id: int = Field(foreign_key="utilisateur.id")
    chemin_fichier: str
    statut: StatutDocument = Field(default=StatutDocument.EN_ATTENTE)
    nb_telechargements: int = Field(default=0)
    date_upload: datetime = Field(default_factory=datetime.utcnow)


class Abonnement(SQLModel, table=True):
    """Abonnement sponsor/repetiteur — c'est ce cote du marche qui paie,
    pas l'etudiant (voir la note sur le modele economique dans le README)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    utilisateur_id: int = Field(foreign_key="utilisateur.id")
    prix_ariary: int
    fournisseur_paiement: Optional[str] = None  # "mvola" / "orange_money" / "airtel_money"
    reference_paiement: Optional[str] = None
    statut: StatutAbonnement = Field(default=StatutAbonnement.EN_ATTENTE_PAIEMENT)
    date_debut: Optional[datetime] = None
    date_fin: Optional[datetime] = None


class CercleEtude(SQLModel, table=True):
    """Un salon de discussion que les etudiants creent pour reviser
    ensemble : par filiere (ex: "Droit civil S3") ou en groupe libre."""
    id: Optional[int] = Field(default=None, primary_key=True)
    nom: str
    description: Optional[str] = None
    filiere_id: Optional[int] = Field(default=None, foreign_key="filiere.id")
    createur_id: int = Field(foreign_key="utilisateur.id")
    date_creation: datetime = Field(default_factory=datetime.utcnow)


class MembreCercle(SQLModel, table=True):
    """Appartenance d'un utilisateur a un cercle d'etude — seuls les
    membres voient et envoient des messages dans le salon."""
    id: Optional[int] = Field(default=None, primary_key=True)
    cercle_id: int = Field(foreign_key="cercleetude.id")
    utilisateur_id: int = Field(foreign_key="utilisateur.id")
    date_adhesion: datetime = Field(default_factory=datetime.utcnow)


class MessageCercle(SQLModel, table=True):
    """Un message envoye dans un cercle d'etude (historique persistant,
    relu a chaque ouverture du salon en plus du flux temps reel)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    cercle_id: int = Field(foreign_key="cercleetude.id")
    auteur_id: int = Field(foreign_key="utilisateur.id")
    contenu: str
    date_envoi: datetime = Field(default_factory=datetime.utcnow)
