"""
Modeles de donnees de GASY MAHAY.

SQLModel = SQLAlchemy + Pydantic en un seul objet : chaque classe ci-dessous
est a la fois une table SQLite ET un schema de validation. C'est ce qui
permet de rester 100% Python sans dupliquer les definitions.
"""
from datetime import date, datetime
from enum import Enum
from typing import Optional

from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Index, text


class RoleUtilisateur(str, Enum):
    ETUDIANT = "etudiant"
    SPONSOR = "sponsor"      # repetiteur, petit commerce, service pour etudiants
    PROFESSEUR = "professeur"  # anime des cours dans le module Classe virtuelle
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


class StatutAbonnementEtudiant(str, Enum):
    """Cycle de vie de l'abonnement Premium d'un etudiant. Distinct de
    StatutAbonnement (qui concerne le sponsoring des repetiteurs/commerces,
    un autre cote du marche avec une autre logique d'activation) : ici
    l'activation passe TOUJOURS par une validation manuelle d'un admin sur
    preuve de paiement, jamais automatique."""
    ESSAI = "essai"                 # essai gratuit de 14 jours, actif automatiquement a l'inscription
    EN_ATTENTE = "en_attente"       # demande soumise (avec ou sans preuve), en attente de validation admin
    ACTIF = "actif"                 # valide par un admin, Premium accessible
    EXPIRE = "expire"               # essai ou abonnement paye arrive a echeance sans renouvellement
    REFUSE = "refuse"               # demande rejetee par un admin (ex: preuve de paiement invalide)


class Universite(SQLModel, table=True):
    """Niveau le plus haut du referentiel academique national (§2-3 du
    brief refonte academique). Une seule ligne existe au depart :
    'Universite de Toamasina', vers laquelle toutes les Faculte
    actuelles sont rattachees par la migration — aucune donnee
    existante n'est perdue ou renumerotee."""
    id: Optional[int] = Field(default=None, primary_key=True)
    nom: str = Field(index=True, unique=True)
    ville: Optional[str] = None
    code: Optional[str] = Field(default=None, unique=True)
    est_active: bool = Field(default=True)

    facultes: list["Faculte"] = Relationship(back_populates="universite")


class Mention(SQLModel, table=True):
    """Regroupement de filieres (ex: 'Sciences de Gestion' regroupe
    Finance et Comptabilite, GRH...). Optionnel sur Filiere (nullable) :
    les filieres existantes ne sont PAS auto-affectees a une mention
    par la migration (cela demanderait de deviner un classement —
    laisse a une revision manuelle via l'admin, voir §44 du brief :
    'la normalisation doit etre faite avec prudence')."""
    id: Optional[int] = Field(default=None, primary_key=True)
    nom: str = Field(index=True, unique=True)
    est_active: bool = Field(default=True)

    filieres: list["Filiere"] = Relationship(back_populates="mention")


class Faculte(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    nom: str = Field(index=True, unique=True)
    # Nullable au niveau du modele Python pour ne jamais bloquer un code
    # qui construirait un Faculte sans le renseigner explicitement, mais
    # la migration la remplit pour toutes les lignes existantes puis
    # pose une contrainte NOT NULL en base (voir la migration :
    # aucune Faculte ne doit rester sans universite).
    universite_id: Optional[int] = Field(default=None, foreign_key="universite.id")

    universite: Optional[Universite] = Relationship(back_populates="facultes")
    filieres: list["Filiere"] = Relationship(back_populates="faculte")


class Filiere(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    nom: str
    faculte_id: int = Field(foreign_key="faculte.id")
    # Nullable expres : voir la docstring de Mention ci-dessus.
    mention_id: Optional[int] = Field(default=None, foreign_key="mention.id")

    faculte: Optional[Faculte] = Relationship(back_populates="filieres")
    mention: Optional[Mention] = Relationship(back_populates="filieres")


class ProgrammeUniversitaire(SQLModel, table=True):
    """Table de liaison (§4 et §7 du brief) : indique qu'une filiere
    globale est proposee dans une universite donnee, pour une annee
    academique donnee. Permet a terme qu'une meme filiere (meme
    filiere_id) soit proposee par plusieurs universites, sans dupliquer
    la filiere elle-meme. La migration seede une ligne par filiere
    existante -> Universite de Toamasina (fait deja vrai, aucune
    invention de donnees)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    universite_id: int = Field(foreign_key="universite.id")
    filiere_id: int = Field(foreign_key="filiere.id")
    annee_academique: Optional[str] = None  # ex: "2026-2027" ; laisse vide = "en cours, sans date de fin connue"
    est_active: bool = Field(default=True)


class Utilisateur(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    nom: str
    # Le telephone sert d'identifiant de connexion : c'est ce que tout le
    # monde utilise deja pour mobile money, plus fiable qu'un email ici.
    telephone: str = Field(index=True, unique=True)
    mot_de_passe_hash: str
    role: RoleUtilisateur = Field(default=RoleUtilisateur.ETUDIANT)
    filiere_id: Optional[int] = Field(default=None, foreign_key="filiere.id")
    # Ajoutes pour le referentiel academique national (§15 du brief) :
    # nullable, les comptes existants n'en ont pas et continuent de
    # fonctionner normalement (aucune fonctionnalite actuelle n'exige
    # ces deux champs). universite_id derive normalement de filiere_id
    # via ProgrammeUniversitaire, mais on le stocke explicitement : un
    # etudiant choisit d'abord SON universite, ce qui restreint ensuite
    # la liste de filieres proposees a l'inscription.
    universite_id: Optional[int] = Field(default=None, foreign_key="universite.id")
    niveau: Optional[str] = None  # voir app/referentiel.py (NIVEAUX)
    # Horodatage de la derniere modification du niveau (§14 de la mise
    # a jour) : permet au backend de faire respecter le delai minimum
    # de 14 jours entre deux changements. None = jamais modifie (donc
    # aucune restriction au premier changement).
    niveau_modifie_le: Optional[datetime] = None
    date_creation: datetime = Field(default_factory=datetime.utcnow)
    banni: bool = Field(default=False)

    # --- Double authentification (TOTP, gratuite — aucun SMS/service
    # tiers, calculee localement par une app comme Google Authenticator).
    # Voir app/routers/auth_router.py. totp_secret reste vide tant que la
    # 2FA n'est pas activee ; totp_active=True seulement apres que
    # l'utilisateur a confirme un code valide (evite un verrouillage si
    # le QR code a ete mal scanne)."""
    totp_secret: Optional[str] = None
    totp_active: bool = Field(default=False)


class CodeSecours2FA(SQLModel, table=True):
    """Codes de secours a usage unique, generes a l'activation de la 2FA,
    pour se reconnecter si l'utilisateur perd l'acces a son application
    d'authentification (telephone perdu/casse/reinstalle). Chaque code
    est hache (jamais stocke en clair, meme si techniquement a usage
    unique) et marque utilise des qu'il sert, plutot que supprime — garde
    une trace de quand chaque code a ete consomme."""
    id: Optional[int] = Field(default=None, primary_key=True)
    utilisateur_id: int = Field(foreign_key="utilisateur.id")
    code_hash: str
    utilise: bool = Field(default=False)
    date_creation: datetime = Field(default_factory=datetime.utcnow)
    date_utilisation: Optional[datetime] = None


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


class TentativeQuiz(SQLModel, table=True):
    """Un quiz genere pour un etudiant : le meme enregistrement sert
    d'abord de 'quiz en cours' (questions generees, pas encore repondu),
    puis devient un resultat d'historique une fois soumis. Les questions
    et les reponses sont stockees en JSON (texte) plutot qu'en tables
    normalisees : structure qui ne varie jamais independamment de la
    tentative, pas besoin de la requeter en dehors de cette tentative."""
    id: Optional[int] = Field(default=None, primary_key=True)
    utilisateur_id: int = Field(foreign_key="utilisateur.id")
    matiere: str
    niveau: str
    difficulte: str
    nb_questions: int
    questions_json: str  # [{question, choix[], index_bonne_reponse, explication}, ...]
    reponses_json: Optional[str] = None  # [index_choisi_ou_null, ...], rempli a la soumission
    score: Optional[int] = None  # nombre de bonnes reponses, rempli a la soumission
    date_creation: datetime = Field(default_factory=datetime.utcnow)
    date_soumission: Optional[datetime] = None
    # --- Mode examen : matiere/niveau/difficulte tires au sort par le
    # serveur (pas choisis par l'etudiant) et chronometre affiche cote
    # client, qui soumet automatiquement le quiz a l'expiration. ---
    mode_examen: bool = Field(default=False)
    duree_secondes: Optional[int] = None


class SignalementQuestionQuiz(SQLModel, table=True):
    """Signalement par un etudiant d'une question/reponse generee par
    l'IA qui lui semble fausse ou incoherente. Traite manuellement par
    un admin (pas de correction automatique — l'IA peut se tromper a
    nouveau en 'corrigeant', mieux vaut un humain qui tranche)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    tentative_id: int = Field(foreign_key="tentativequiz.id")
    index_question: int  # position (0-based) dans questions_json de la tentative
    signale_par_id: int = Field(foreign_key="utilisateur.id")
    motif: Optional[str] = None
    date_signalement: datetime = Field(default_factory=datetime.utcnow)
    traite: bool = Field(default=False)


class ConsultationDocument(SQLModel, table=True):
    """Trace qu'un etudiant a consulte/telecharge un document, pour
    alimenter le 'derniers documents consultes' du tableau de bord.
    Un enregistrement par consultation (pas de deduplication en base) :
    c'est au moment de la lecture qu'on ne garde que la plus recente par
    document. Uniquement enregistre pour les telechargements connectes
    (le telechargement reste possible sans compte, comme avant)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    utilisateur_id: int = Field(foreign_key="utilisateur.id")
    document_id: int = Field(foreign_key="document.id")
    date_consultation: datetime = Field(default_factory=datetime.utcnow)


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


class StatutCercle(str, Enum):
    ACTIF = "actif"
    ARCHIVE = "archive"


class RoleMembreCercle(str, Enum):
    CREATEUR = "createur"
    MEMBRE = "membre"


class CercleEtude(SQLModel, table=True):
    """Un salon de discussion national : les etudiants de TOUTES les
    universites partageant la meme (mention, filiere, niveau) se
    retrouvent dans le meme cercle (mise a jour du brief : "L'universite
    n'est pas une frontiere", §2 et §17). Un cercle peut aussi rester un
    simple groupe libre transversal (mention_id/filiere_id/niveau tous
    None), comme avant cette evolution."""
    id: Optional[int] = Field(default=None, primary_key=True)
    nom: str
    description: Optional[str] = None
    filiere_id: Optional[int] = Field(default=None, foreign_key="filiere.id")
    # Denormalise a dessein (deductible via filiere.mention_id) : le
    # brief definit explicitement l'identite d'un cercle comme le
    # triplet (mention_id, filiere_id, niveau) — §27 : "Ne pas utiliser
    # university_id pour determiner l'identite du cercle", la mention
    # fait partie de cette identite au meme titre que la filiere.
    # Nullable : les cercles groupe-libre ou dont la filiere n'a pas
    # encore de mention assignee (voir Filiere.mention_id, laisse NULL
    # tant que non verifie manuellement) restent valides sans mention.
    mention_id: Optional[int] = Field(default=None, foreign_key="mention.id")
    niveau: Optional[str] = None
    statut: StatutCercle = Field(default=StatutCercle.ACTIF)
    createur_id: int = Field(foreign_key="utilisateur.id")
    date_creation: datetime = Field(default_factory=datetime.utcnow)

    # Reflete exactement l'index cree par la migration e1a4c9d2b7f5
    # (ix_cercle_national_unique_actif) : declare ici aussi pour que
    # SQLModel.metadata.create_all() (utilise par les tests et par tout
    # outil d'introspection future) reste coherent avec le vrai schema
    # de production, plutot que de ne connaitre l'index que via la
    # migration.
    __table_args__ = (
        Index(
            "ix_cercle_national_unique_actif",
            "mention_id", "filiere_id", "niveau",
            unique=True,
            sqlite_where=text("statut = 'ACTIF' AND mention_id IS NOT NULL AND filiere_id IS NOT NULL AND niveau IS NOT NULL"),
            postgresql_where=text("statut = 'ACTIF' AND mention_id IS NOT NULL AND filiere_id IS NOT NULL AND niveau IS NOT NULL"),
        ),
    )


class MembreCercle(SQLModel, table=True):
    """Appartenance d'un utilisateur a un cercle d'etude — seuls les
    membres voient et envoient des messages dans le salon."""
    id: Optional[int] = Field(default=None, primary_key=True)
    cercle_id: int = Field(foreign_key="cercleetude.id")
    utilisateur_id: int = Field(foreign_key="utilisateur.id")
    # Le createur du cercle a toujours role=CREATEUR (voir §23 du brief) ;
    # backfille par la migration a partir de CercleEtude.createur_id
    # pour toutes les lignes existantes, donc jamais NULL en pratique
    # malgre le defaut MEMBRE ici (defaut de securite si jamais une
    # ligne etait creee sans passer par le flux normal).
    role: RoleMembreCercle = Field(default=RoleMembreCercle.MEMBRE)
    date_adhesion: datetime = Field(default_factory=datetime.utcnow)


class ThemeDuJour(SQLModel, table=True):
    """Correspond exactement au schema cree par la migration
    6ce046f6408e ('theme du jour unique avec cercle dedie') : cette
    table existait deja en base sans modele ORM associe dans le code
    (le reste de la fonctionnalite n'avait jamais ete commite). Un
    theme par date_jour (unique), avec un lien optionnel vers un cercle
    dedie a la discussion de ce theme ce jour-la."""
    id: Optional[int] = Field(default=None, primary_key=True)
    date_jour: date = Field(index=True, unique=True)
    theme: str
    amorce: str
    cercle_id: Optional[int] = Field(default=None, foreign_key="cercleetude.id")
    date_creation: datetime = Field(default_factory=datetime.utcnow)


class StatutDemandeAdhesion(str, Enum):
    EN_ATTENTE = "en_attente"
    ACCEPTEE = "acceptee"
    REJETEE = "rejetee"


class DemandeAdhesionCercle(SQLModel, table=True):
    """Demande d'un utilisateur pour rejoindre un cercle. Doit etre
    examinee (accepter/refuser) par le createur du cercle ou un admin
    avant que l'utilisateur devienne reellement membre (voir
    app/routers/cercles_router.py). Une seule demande EN_ATTENTE par
    (cercle_id, utilisateur_id) — voir la migration pour la contrainte
    d'unicite partielle cote base, doublee d'une verification
    applicative pour rester compatible SQLite."""
    id: Optional[int] = Field(default=None, primary_key=True)
    cercle_id: int = Field(foreign_key="cercleetude.id")
    utilisateur_id: int = Field(foreign_key="utilisateur.id")
    # Nullable en base (les demandes existantes n'en ont pas), mais le
    # prochain formulaire de demande d'adhesion devra l'exiger cote
    # route pour les nouvelles demandes (§21 du brief : "Pourquoi
    # souhaitez-vous rejoindre ce cercle ?" obligatoire) — pas encore
    # branche a ce stade (modeles/migration seulement).
    raison: Optional[str] = None
    statut: StatutDemandeAdhesion = Field(default=StatutDemandeAdhesion.EN_ATTENTE)
    date_creation: datetime = Field(default_factory=datetime.utcnow)
    date_traitement: Optional[datetime] = None
    traite_par_id: Optional[int] = Field(default=None, foreign_key="utilisateur.id")


class StatutDemandeCreationCercle(str, Enum):
    EN_ATTENTE = "en_attente"
    APPROUVEE = "approuvee"
    REJETEE = "rejetee"


class DemandeCreationCercle(SQLModel, table=True):
    """Demande de creation d'un cercle NATIONAL (§20-24 de la mise a
    jour) : la creation n'est plus directe, elle passe par une
    validation admin. Non encore branchee a ce stade (schema seulement)
    — la creation directe actuelle (cercles_router.creer_cercle)
    continue de fonctionner sans changement tant que ce nouveau flux
    n'est pas active."""
    id: Optional[int] = Field(default=None, primary_key=True)
    utilisateur_id: int = Field(foreign_key="utilisateur.id")
    mention_id: Optional[int] = Field(default=None, foreign_key="mention.id")
    filiere_id: Optional[int] = Field(default=None, foreign_key="filiere.id")
    niveau: Optional[str] = None
    nom: str
    description: Optional[str] = None
    raison: str
    statut: StatutDemandeCreationCercle = Field(default=StatutDemandeCreationCercle.EN_ATTENTE)
    date_creation: datetime = Field(default_factory=datetime.utcnow)
    date_traitement: Optional[datetime] = None
    traite_par_id: Optional[int] = Field(default=None, foreign_key="utilisateur.id")
    # Rempli seulement quand la demande est approuvee (le cercle est
    # alors reellement cree) — permet de retrouver le cercle issu de
    # cette demande depuis l'historique admin.
    cercle_cree_id: Optional[int] = Field(default=None, foreign_key="cercleetude.id")


class StatutDemandeChangementFiliere(str, Enum):
    EN_ATTENTE = "en_attente"
    APPROUVEE = "approuvee"
    REJETEE = "rejetee"


class DemandeChangementFiliere(SQLModel, table=True):
    """Prepare le changement de filiere (§17 du brief) : schema pret,
    non branche a l'UI pour cette premiere version (non bloquant pour
    le reste). Un etudiant ne peut pas modifier filiere_id directement
    depuis son profil (§16) — ce sera, plus tard, le seul chemin pour
    en changer, apres validation admin."""
    id: Optional[int] = Field(default=None, primary_key=True)
    utilisateur_id: int = Field(foreign_key="utilisateur.id")
    ancienne_filiere_id: Optional[int] = Field(default=None, foreign_key="filiere.id")
    nouvelle_filiere_id: int = Field(foreign_key="filiere.id")
    motif: str
    statut: StatutDemandeChangementFiliere = Field(default=StatutDemandeChangementFiliere.EN_ATTENTE)
    date_creation: datetime = Field(default_factory=datetime.utcnow)
    date_traitement: Optional[datetime] = None
    traite_par_id: Optional[int] = Field(default=None, foreign_key="utilisateur.id")


class MessageCercle(SQLModel, table=True):
    """Un message envoye dans un cercle d'etude (historique persistant,
    relu a chaque ouverture du salon en plus du flux temps reel)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    cercle_id: int = Field(foreign_key="cercleetude.id")
    auteur_id: int = Field(foreign_key="utilisateur.id")
    contenu: str
    date_envoi: datetime = Field(default_factory=datetime.utcnow)
    # Partage de fichier (PDF) : optionnel, un message peut etre texte
    # seul, fichier seul, ou les deux.
    piece_jointe_chemin: Optional[str] = None
    piece_jointe_nom: Optional[str] = None
    # Suppression douce (moderation) : le message reste en base pour
    # l'historique/audit, mais n'est plus affiche ni diffuse en clair.
    supprime: bool = Field(default=False)


class SignalementMessage(SQLModel, table=True):
    """Signalement d'un message par un membre du cercle, a traiter par un
    admin (voir/supprimer le message, ou rejeter le signalement)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    message_id: int = Field(foreign_key="messagecercle.id")
    signale_par_id: int = Field(foreign_key="utilisateur.id")
    motif: Optional[str] = None
    date_signalement: datetime = Field(default_factory=datetime.utcnow)
    traite: bool = Field(default=False)


class AbonnementEtudiant(SQLModel, table=True):
    """Acces Premium d'un etudiant : demarre automatiquement en essai
    gratuit de 14 jours a l'inscription, puis (optionnellement) en
    abonnement paye de 10 000 Ar/mois valide manuellement par un admin sur
    preuve de paiement hors-ligne (Mobile Money / virement).

    Un seul enregistrement par etudiant : on ne cree pas une ligne par
    cycle de paiement, on prolonge celui-ci (date_fin += 30 jours a chaque
    validation admin) — plus simple a interroger pour "l'etudiant a-t-il
    acces au Premium en ce moment", et l'historique des demandes reste de
    toute facon dans le fichier de preuve + les dates deja enregistrees.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    utilisateur_id: int = Field(foreign_key="utilisateur.id", unique=True)
    statut: StatutAbonnementEtudiant = Field(default=StatutAbonnementEtudiant.ESSAI)

    # --- Essai gratuit ---
    date_debut_essai: datetime = Field(default_factory=datetime.utcnow)
    date_fin_essai: datetime

    # --- Abonnement paye (rempli seulement une fois une demande soumise) ---
    date_fin_abonnement: Optional[datetime] = None
    preuve_paiement_chemin: Optional[str] = None
    fournisseur_paiement: Optional[str] = None  # "mvola" / "orange_money" / "airtel_money" / "virement"
    reference_paiement: Optional[str] = None

    # --- Tracabilite de la derniere action admin ---
    valide_par_admin_id: Optional[int] = Field(default=None, foreign_key="utilisateur.id")
    date_derniere_action_admin: Optional[datetime] = None
    motif_refus: Optional[str] = None

    date_maj: datetime = Field(default_factory=datetime.utcnow)


class SessionTuteur(SQLModel, table=True):
    """Un echange avec le tuteur IA : l'etudiant pose une question libre,
    l'IA repond en 4 parties structurees (explication, exemple, exercice,
    correction). Un enregistrement par question posee — sert aussi
    d'historique consultable plus tard."""
    id: Optional[int] = Field(default=None, primary_key=True)
    utilisateur_id: int = Field(foreign_key="utilisateur.id")
    question: str
    explication: str
    exemple: str
    exercice: str
    correction: str
    date_creation: datetime = Field(default_factory=datetime.utcnow)


# ============================================================
# Classe virtuelle — voir app/routers/classe_router.py
# ============================================================
# Modelise volontairement sur le meme schema que les cercles d'etude
# (createur/proprietaire + inscription + messages) plutot que d'inventer
# un systeme parallele : Cours ~ CercleEtude, InscriptionCours ~
# MembreCercle, Seance ajoute juste la notion de creneau/salle vivante.

class StatutSeance(str, Enum):
    PLANIFIEE = "planifiee"
    EN_COURS = "en_cours"
    TERMINEE = "terminee"


class Cours(SQLModel, table=True):
    """Un cours anime par un professeur (role PROFESSEUR uniquement —
    voir _est_professeur_du_cours dans classe_router.py). Contient
    plusieurs Seance. Les etudiants y participent via InscriptionCours."""
    id: Optional[int] = Field(default=None, primary_key=True)
    nom: str
    matiere: str
    niveau: str
    description: Optional[str] = None
    professeur_id: int = Field(foreign_key="utilisateur.id")
    date_creation: datetime = Field(default_factory=datetime.utcnow)


class InscriptionCours(SQLModel, table=True):
    """Un etudiant inscrit a un cours (ajoute directement par le
    professeur, meme logique que l'ajout de membre par telephone dans
    les cercles — pas de workflow de demande ici, cf. cahier des charges
    'inviter ou ajouter des etudiants')."""
    id: Optional[int] = Field(default=None, primary_key=True)
    cours_id: int = Field(foreign_key="cours.id")
    utilisateur_id: int = Field(foreign_key="utilisateur.id")
    date_inscription: datetime = Field(default_factory=datetime.utcnow)


class Seance(SQLModel, table=True):
    """Une seance planifiee d'un cours. Le nom_salle_livekit est genere
    a la creation (unique, stable) — c'est lui qui identifie la salle
    LiveKit ; la salle elle-meme n'existe reellement cote LiveKit que le
    temps ou des participants y sont connectes (LiveKit gere ca tout
    seul, rien a provisionner a l'avance cote MAHAY)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    cours_id: int = Field(foreign_key="cours.id")
    titre: str
    description: Optional[str] = None
    statut: StatutSeance = Field(default=StatutSeance.PLANIFIEE)
    nom_salle_livekit: str = Field(unique=True)
    date_debut_reelle: Optional[datetime] = None
    date_fin_reelle: Optional[datetime] = None
    date_creation: datetime = Field(default_factory=datetime.utcnow)


class PresenceSeance(SQLModel, table=True):
    """Une ligne par (seance, utilisateur) ayant rejoint la salle au
    moins une fois. heure_sortie reste vide tant que l'utilisateur est
    connecte ; mise a jour a chaque 'quitter' (et re-ouverte si la
    personne revient et repart plusieurs fois — on garde la derniere
    sortie, la duree_estimee_secondes cumule au fil des allers-retours)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    seance_id: int = Field(foreign_key="seance.id")
    utilisateur_id: int = Field(foreign_key="utilisateur.id")
    heure_entree: datetime = Field(default_factory=datetime.utcnow)
    heure_sortie: Optional[datetime] = None
    duree_estimee_secondes: int = Field(default=0)


# ============================================================
# Tableau blanc collaboratif — voir app/routers/classe_router.py
# ============================================================

class TypeEvenementTableau(str, Enum):
    TRAIT = "trait"              # dessin libre (liste de points)
    FORME = "forme"               # rectangle/cercle/ligne
    TEXTE = "texte"
    SUPPRESSION = "suppression"   # annule un element precis (undo/effacement cible)
    EFFACER_TOUT = "effacer_tout"


class EvenementTableauBlanc(SQLModel, table=True):
    """Journal append-only de tout ce qui se passe sur le tableau blanc
    d'une seance. Ne JAMAIS modifier/supprimer une ligne existante — un
    'undo' ajoute une nouvelle ligne de type SUPPRESSION qui reference
    l'element vise, un 'redo' ajoute une nouvelle ligne qui recree
    l'element original (meme element_id). Cette approche (plutot que
    modifier en place) permet de reconstituer l'etat exact du tableau a
    tout moment en rejouant le journal dans l'ordre — necessaire pour
    qu'un etudiant qui rejoint en retard voie le tableau tel qu'il est
    actuellement (voir _reconstituer_etat_tableau dans classe_router.py)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    seance_id: int = Field(foreign_key="seance.id")
    utilisateur_id: int = Field(foreign_key="utilisateur.id")
    type_evenement: TypeEvenementTableau
    element_id: str  # identifiant genere cote client (un dessin = un id stable)
    donnees: str = "{}"  # JSON serialise : points/couleur/epaisseur/texte/coords selon le type
    date_creation: datetime = Field(default_factory=datetime.utcnow)


class AutorisationEcritureTableau(SQLModel, table=True):
    """Un etudiant explicitement autorise par le professeur (ou un admin)
    a dessiner sur le tableau de CETTE seance precise, en plus du
    prof/admin qui peuvent toujours ecrire. La ligne est supprimee quand
    l'autorisation est revoquee — sa seule presence fait foi, pas de
    champ 'actif' a verifier en plus."""
    id: Optional[int] = Field(default=None, primary_key=True)
    seance_id: int = Field(foreign_key="seance.id")
    utilisateur_id: int = Field(foreign_key="utilisateur.id")
    date_creation: datetime = Field(default_factory=datetime.utcnow)


# ============================================================
# Devoirs & rendus — voir app/routers/classe_router.py
# ============================================================

class Devoir(SQLModel, table=True):
    """Un devoir/exercice attache a un Cours (pas a une Seance precise :
    un devoir peut couvrir plusieurs seances). date_limite optionnelle —
    si absente, aucune deadline n'est appliquee."""
    id: Optional[int] = Field(default=None, primary_key=True)
    cours_id: int = Field(foreign_key="cours.id")
    titre: str
    description: Optional[str] = None
    date_limite: Optional[datetime] = None
    date_creation: datetime = Field(default_factory=datetime.utcnow)


class RenduDevoir(SQLModel, table=True):
    """Le rendu d'un etudiant pour un devoir. Un etudiant peut re-rendre
    (ecrase le rendu precedent — voir rendre_devoir()) tant que la date
    limite n'est pas depassee. note/appreciation restent vides tant que
    le professeur n'a pas corrige."""
    id: Optional[int] = Field(default=None, primary_key=True)
    devoir_id: int = Field(foreign_key="devoir.id")
    utilisateur_id: int = Field(foreign_key="utilisateur.id")
    chemin_fichier: str
    nom_fichier_original: str
    commentaire: Optional[str] = None
    date_rendu: datetime = Field(default_factory=datetime.utcnow)
    note: Optional[float] = None
    appreciation_prof: Optional[str] = None
    date_correction: Optional[datetime] = None
