"""Préinscription institutionnelle sécurisée de groupes d'étudiants."""
from __future__ import annotations

import csv
from datetime import datetime
import io
import re
import secrets
import unicodedata
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, func, select

from ..auth import hacher_mot_de_passe, utilisateur_courant
from ..csrf import verifier_csrf
from ..database import get_session
from ..models import (
    EtablissementPartenaire, MembreEtablissement, RoleMembreEtablissement,
    RoleUtilisateur, StatutMembreEtablissement, Utilisateur,
)
from ..telephone import TelephoneInvalide, normaliser_telephone
from ..templating import templates
from ..subscription import creer_essais_gratuits_en_masse

router = APIRouter()
TAILLE_MAX_FICHIER = 5 * 1024 * 1024
MAX_ETUDIANTS_PAR_IMPORT = 500
LONGUEUR_MAX_NOM = 120


def _admin_requis(request: Request, session: Session) -> Optional[Utilisateur]:
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur or utilisateur.role != RoleUtilisateur.ADMIN:
        return None
    return utilisateur


def _ascii(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    return "".join(c for c in value if not unicodedata.combining(c))


def normaliser_code_institution(value: str) -> str:
    value = _ascii(value).strip().upper()
    value = re.sub(r"[^A-Z0-9_-]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-_")
    if not 2 <= len(value) <= 32 or not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]*", value):
        raise ValueError("Le code doit contenir 2 à 32 lettres, chiffres, tirets ou soulignements.")
    return value


def normaliser_matricule(value: str) -> str:
    value = _ascii(str(value or "")).strip().upper()
    value = re.sub(r"\s+", "-", value)
    value = re.sub(r"[^A-Z0-9._/-]", "", value)
    if not value or len(value) > 80 or not re.search(r"[A-Z0-9]", value):
        raise ValueError("Matricule absent ou invalide.")
    return value


def identifiant_etudiant(code_institution: str, matricule: str) -> str:
    code = normaliser_code_institution(code_institution)
    matricule_normalise = normaliser_matricule(matricule)
    suffixe = re.sub(r"[^A-Z0-9_-]+", "-", matricule_normalise).strip("-_")
    if not suffixe:
        raise ValueError("Le matricule ne permet pas de créer un identifiant.")
    identifiant = f"{code}-{suffixe}"
    if len(identifiant) > 160:
        raise ValueError("L'identifiant généré est trop long.")
    return identifiant


def _cle_entete(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", _ascii(str(value or "")).lower())


ALIASES = {
    "nom": {"nom", "nomcomplet", "nometprenom", "nometudiant", "fullname", "studentname", "name"},
    "prenom": {"prenom", "prenoms", "firstname", "givenname"},
    "matricule": {"matricule", "matriculeetudiant", "numeroetudiant", "numerodetudiant", "numetudiant", "identifiantetudiant", "studentid", "studentnumber", "registrationnumber"},
    "telephone": {"telephone", "tel", "phone", "phonenumber", "numerodetelephone"},
    "email": {"email", "courriel", "adressemail", "adresseemail"},
    "niveau": {"niveau", "classe", "level", "class"},
}


def _lignes_csv(contenu: bytes) -> list[list[object]]:
    try:
        texte = contenu.decode("utf-8-sig")
    except UnicodeDecodeError:
        texte = contenu.decode("cp1252")
    try:
        separateur = csv.Sniffer().sniff(texte[:8192], delimiters=";,\t|").delimiter
    except csv.Error:
        separateur = ";"
    lecteur = csv.reader(io.StringIO(texte), delimiter=separateur)
    lignes: list[list[object]] = []
    for ligne in lecteur:
        if not any(str(cellule or "").strip() for cellule in ligne):
            continue
        lignes.append(ligne)
        if len(lignes) > MAX_ETUDIANTS_PAR_IMPORT + 1:
            raise ValueError(f"Limite atteinte : maximum {MAX_ETUDIANTS_PAR_IMPORT} étudiants par import.")
    return lignes


def lire_lignes_tableur(nom_fichier: str, contenu: bytes) -> list[dict[str, str]]:
    """Lit un CSV/XLSX court en texte ; refuse les fichiers inconnus ou trop volumineux."""
    if len(contenu) > TAILLE_MAX_FICHIER:
        raise ValueError("Le fichier dépasse la limite de 5 Mo.")
    extension = (nom_fichier.rsplit(".", 1)[-1] if "." in nom_fichier else "").lower()
    if extension == "csv":
        lignes = _lignes_csv(contenu)
    elif extension == "xlsx":
        try:
            from openpyxl import load_workbook
            classeur = load_workbook(io.BytesIO(contenu), read_only=True, data_only=True)
            try:
                feuille = classeur.active
                lignes = []
                for ligne in feuille.iter_rows(values_only=True):
                    valeurs = list(ligne)
                    if any(str(cellule or "").strip() for cellule in valeurs):
                        lignes.append(valeurs)
                        if len(lignes) > MAX_ETUDIANTS_PAR_IMPORT + 1:
                            raise ValueError(
                                f"Limite atteinte : maximum {MAX_ETUDIANTS_PAR_IMPORT} étudiants par import."
                            )
            finally:
                classeur.close()
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("Le fichier Excel est illisible ou endommagé.") from exc
    else:
        raise ValueError("Format non pris en charge : utilise un fichier .csv ou .xlsx.")

    lignes = [ligne for ligne in lignes if any(str(cellule or "").strip() for cellule in ligne)]
    if not lignes:
        raise ValueError("Le fichier ne contient aucune ligne.")
    entetes = [_cle_entete(cellule) for cellule in lignes[0]]
    colonnes: dict[str, int] = {}
    for nom, aliases in ALIASES.items():
        index = next((i for i, valeur in enumerate(entetes) if valeur in aliases), None)
        if index is not None:
            colonnes[nom] = index
    if "nom" not in colonnes or "matricule" not in colonnes:
        raise ValueError("Colonnes requises introuvables : nom (ou nom complet) et matricule (ou numéro étudiant).")
    enregistrements: list[dict[str, str]] = []
    for no_ligne, ligne in enumerate(lignes[1:], start=2):
        def valeur(nom: str) -> str:
            index = colonnes.get(nom)
            if index is None or index >= len(ligne):
                return ""
            valeur_cellule = ligne[index]
            return str(valeur_cellule).strip() if valeur_cellule is not None else ""
        nom = valeur("nom")
        prenom = valeur("prenom")
        if prenom and _cle_entete(lignes[0][colonnes["nom"]]) in {"nom", "name"}:
            nom = f"{nom} {prenom}".strip()
        enregistrements.append({
            "ligne": str(no_ligne),
            "nom": nom,
            "matricule": valeur("matricule"),
            "telephone": valeur("telephone"),
            "email": valeur("email"),
            "niveau": valeur("niveau"),
        })
        if len(enregistrements) > MAX_ETUDIANTS_PAR_IMPORT:
            raise ValueError(f"Limite atteinte : maximum {MAX_ETUDIANTS_PAR_IMPORT} étudiants par import.")
    if not enregistrements:
        raise ValueError("Le fichier ne contient aucun étudiant à importer.")
    return enregistrements


def _page(request: Request, session: Session, admin: Utilisateur, *, erreur: str | None = None,
          resultat: list[dict[str, str]] | None = None, lignes_erreur: list[str] | None = None,
          institution_selectionnee: int | None = None):
    institutions = session.exec(
        select(EtablissementPartenaire).order_by(EtablissementPartenaire.nom)
    ).all()
    effectifs = dict(session.exec(
        select(Utilisateur.institution_id, func.count(Utilisateur.id))
        .where(Utilisateur.institution_id.is_not(None))
        .group_by(Utilisateur.institution_id)
    ).all())
    return templates.TemplateResponse(request, "admin_inscriptions_institutionnelles.html", {
        "utilisateur": admin,
        "institutions": institutions,
        "effectifs": effectifs,
        "erreur": erreur,
        "resultat": resultat or [],
        "lignes_erreur": lignes_erreur or [],
        "institution_selectionnee": institution_selectionnee,
        "max_etudiants": MAX_ETUDIANTS_PAR_IMPORT,
        "max_mo": TAILLE_MAX_FICHIER // (1024 * 1024),
    }, headers={"Cache-Control": "no-store, private", "Pragma": "no-cache", "X-Robots-Tag": "noindex, nofollow"})


@router.get("/admin/inscriptions-institutionnelles")
def page_inscriptions_institutionnelles(request: Request, session: Session = Depends(get_session)):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/connexion", status_code=303)
    return _page(request, session, admin)


@router.post("/admin/inscriptions-institutionnelles/etablissements")
def creer_etablissement_partenaire(
    request: Request,
    nom: str = Form(...),
    code: str = Form(...),
    type_etablissement: str = Form("universite"),
    region: str = Form(""),
    commune: str = Form(""),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/connexion", status_code=303)
    nom = " ".join((nom or "").split())
    if not nom or len(nom) > 200:
        return _page(request, session, admin, erreur="Le nom de l’établissement est obligatoire (200 caractères maximum).")
    try:
        code_normalise = normaliser_code_institution(code)
    except ValueError as exc:
        return _page(request, session, admin, erreur=str(exc))
    type_normalise = (type_etablissement or "universite").strip().lower()
    if type_normalise not in {"universite", "college_lycee", "etfp", "autre"}:
        return _page(request, session, admin, erreur="Type d’établissement invalide.")
    if session.exec(select(EtablissementPartenaire).where(EtablissementPartenaire.code == code_normalise)).first():
        return _page(request, session, admin, erreur="Ce code d’établissement est déjà utilisé.")
    session.add(EtablissementPartenaire(
        nom=nom, code=code_normalise, type_etablissement=type_normalise,
        region=(region.strip() or None), commune=(commune.strip() or None),
        cree_par_id=admin.id,
    ))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return _page(request, session, admin, erreur="Création impossible : le code existe déjà.")
    return RedirectResponse("/admin/inscriptions-institutionnelles?ok=etablissement_cree", status_code=303)


@router.post("/admin/inscriptions-institutionnelles/importer")
async def importer_etudiants_institutionnels(
    request: Request,
    institution_id: int = Form(...),
    fichier: UploadFile = File(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    admin = _admin_requis(request, session)
    if not admin:
        return RedirectResponse("/connexion", status_code=303)
    institution = session.get(EtablissementPartenaire, institution_id)
    if not institution or not institution.est_actif:
        return _page(request, session, admin, erreur="Choisis un établissement partenaire actif.")
    nom_fichier = fichier.filename or ""
    contenu = await fichier.read(TAILLE_MAX_FICHIER + 1)
    await fichier.close()
    try:
        lignes = lire_lignes_tableur(nom_fichier, contenu)
    except ValueError as exc:
        return _page(request, session, admin, erreur=str(exc), institution_selectionnee=institution.id)

    resultat: list[dict[str, str]] = []
    comptes_crees: list[Utilisateur] = []
    lignes_erreur: list[str] = []
    matricules_vus: set[str] = set()
    identifiants_vus: set[str] = set()
    telephones_vus: set[str] = set()
    for entree in lignes:
        no_ligne = entree["ligne"]
        nom = " ".join(entree["nom"].split())
        if not nom or len(nom) > LONGUEUR_MAX_NOM:
            lignes_erreur.append(f"Ligne {no_ligne} : nom absent ou trop long (120 caractères maximum).")
            continue
        try:
            matricule = normaliser_matricule(entree["matricule"])
            login = identifiant_etudiant(institution.code, matricule)
        except ValueError as exc:
            lignes_erreur.append(f"Ligne {no_ligne} : {exc}")
            continue
        if matricule in matricules_vus:
            lignes_erreur.append(f"Ligne {no_ligne} : matricule présent plusieurs fois dans le fichier.")
            continue
        if login in identifiants_vus:
            lignes_erreur.append(f"Ligne {no_ligne} : identifiant généré en double.")
            continue
        if session.exec(select(Utilisateur).where(
            Utilisateur.institution_id == institution.id,
            Utilisateur.matricule_institutionnel == matricule,
        )).first():
            lignes_erreur.append(f"Ligne {no_ligne} : ce matricule est déjà inscrit dans l’établissement.")
            continue
        if session.exec(select(Utilisateur).where(Utilisateur.identifiant_connexion == login)).first():
            lignes_erreur.append(f"Ligne {no_ligne} : cet identifiant de connexion existe déjà.")
            continue

        telephone = None
        if entree["telephone"]:
            try:
                telephone = normaliser_telephone(entree["telephone"])
            except TelephoneInvalide:
                lignes_erreur.append(f"Ligne {no_ligne} : numéro de téléphone invalide.")
                continue
            if telephone in telephones_vus or session.exec(
                select(Utilisateur).where(Utilisateur.telephone == telephone)
            ).first():
                lignes_erreur.append(f"Ligne {no_ligne} : ce numéro de téléphone est déjà associé à un compte.")
                continue

        email = entree["email"].strip().lower() or None
        if email and (len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)):
            lignes_erreur.append(f"Ligne {no_ligne} : adresse email invalide.")
            continue
        niveau = entree["niveau"].strip()[:80] or None
        mot_de_passe_temporaire = secrets.token_urlsafe(9)
        compte = Utilisateur(
            nom=nom,
            telephone=telephone,
            identifiant_connexion=login,
            institution_id=institution.id,
            matricule_institutionnel=matricule,
            email=email,
            mot_de_passe_hash=hacher_mot_de_passe(mot_de_passe_temporaire),
            role=RoleUtilisateur.ETUDIANT,
            profil_souhaite="eleve",
            niveau=niveau,
            doit_changer_mot_de_passe=True,
        )
        session.add(compte)
        comptes_crees.append(compte)
        resultat.append({
            "nom": nom,
            "matricule": matricule,
            "identifiant": login,
            "mot_de_passe_temporaire": mot_de_passe_temporaire,
        })
        matricules_vus.add(matricule)
        identifiants_vus.add(login)
        if telephone:
            telephones_vus.add(telephone)

    if not resultat:
        session.rollback()
        return _page(request, session, admin, erreur="Aucun compte créé. Vérifie les lignes signalées et corrige le fichier.",
                     lignes_erreur=lignes_erreur, institution_selectionnee=institution.id)
    try:
        # Attribue les identifiants puis crée les essais Premium standards en
        # une transaction de groupe, sans effectuer un commit par étudiant.
        session.flush()
        for compte in comptes_crees:
            session.add(MembreEtablissement(
                institution_id=institution.id,
                utilisateur_id=compte.id,
                role=RoleMembreEtablissement.ETUDIANT.value,
                statut=StatutMembreEtablissement.ACTIF.value,
                cree_par_id=admin.id,
                modifie_par_id=admin.id,
            ))
        session.flush()
        creer_essais_gratuits_en_masse(session, comptes_crees)
        session.commit()
    except IntegrityError:
        session.rollback()
        return _page(request, session, admin,
                     erreur="La base a détecté un doublon pendant l'import. Aucun mot de passe n'a été conservé. Corrige les doublons puis réessaie.",
                     lignes_erreur=lignes_erreur, institution_selectionnee=institution.id)

    return _page(request, session, admin, resultat=resultat, lignes_erreur=lignes_erreur,
                 institution_selectionnee=institution.id)


# --- Gestion des équipes et des appartenances institutionnelles ----------------

ROLE_MEMBRE_LABELS = {
    RoleMembreEtablissement.RESPONSABLE.value: "Responsable",
    RoleMembreEtablissement.GESTIONNAIRE.value: "Gestionnaire",
    RoleMembreEtablissement.ENSEIGNANT.value: "Enseignant",
    RoleMembreEtablissement.ETUDIANT.value: "Apprenant",
}
RANG_ROLE_MEMBRE = {
    RoleMembreEtablissement.ETUDIANT.value: 1,
    RoleMembreEtablissement.ENSEIGNANT.value: 2,
    RoleMembreEtablissement.GESTIONNAIRE.value: 3,
    RoleMembreEtablissement.RESPONSABLE.value: 4,
}


def roles_assignables(role_acteur: str | None, administrateur_global: bool = False) -> list[str]:
    """Rôles locaux que l'acteur peut attribuer ; le responsable reste réservé au global admin."""
    if administrateur_global:
        return list(ROLE_MEMBRE_LABELS)
    role = str(getattr(role_acteur, "value", role_acteur) or "")
    if role == RoleMembreEtablissement.RESPONSABLE.value:
        return [
            RoleMembreEtablissement.GESTIONNAIRE.value,
            RoleMembreEtablissement.ENSEIGNANT.value,
            RoleMembreEtablissement.ETUDIANT.value,
        ]
    if role == RoleMembreEtablissement.GESTIONNAIRE.value:
        return [
            RoleMembreEtablissement.ENSEIGNANT.value,
            RoleMembreEtablissement.ETUDIANT.value,
        ]
    return []


def peut_gerer_role(role_acteur: str | None, role_cible: str | None, administrateur_global: bool = False) -> bool:
    """Interdit à un acteur local de modifier un membre de rang égal ou supérieur."""
    if administrateur_global:
        return True
    acteur = str(getattr(role_acteur, "value", role_acteur) or "")
    cible = str(getattr(role_cible, "value", role_cible) or "")
    return RANG_ROLE_MEMBRE.get(acteur, 0) > RANG_ROLE_MEMBRE.get(cible, 99)


def _contexte_gestion_institution(request: Request, session: Session, institution_id: int):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        raise HTTPException(status_code=401, detail="Connexion requise.")
    institution = session.get(EtablissementPartenaire, institution_id)
    if not institution:
        raise HTTPException(status_code=404, detail="Établissement introuvable.")
    administrateur_global = utilisateur.role == RoleUtilisateur.ADMIN
    membre_acteur = None
    role_acteur = "admin" if administrateur_global else None
    if not administrateur_global:
        membre_acteur = session.exec(
            select(MembreEtablissement).where(
                MembreEtablissement.institution_id == institution.id,
                MembreEtablissement.utilisateur_id == utilisateur.id,
                MembreEtablissement.statut == StatutMembreEtablissement.ACTIF.value,
            )
        ).first()
        if (
            not institution.est_actif
            or not membre_acteur
            or membre_acteur.role not in {
                RoleMembreEtablissement.RESPONSABLE.value,
                RoleMembreEtablissement.GESTIONNAIRE.value,
            }
        ):
            raise HTTPException(status_code=403, detail="Tu n'as pas les droits de gestion de cet établissement.")
        role_acteur = membre_acteur.role
    return utilisateur, institution, role_acteur, administrateur_global


def _page_gestion_membres(
    request: Request,
    session: Session,
    utilisateur: Utilisateur,
    institution: EtablissementPartenaire,
    role_acteur: str,
    administrateur_global: bool,
    erreur: str | None = None,
):
    paires = session.exec(
        select(MembreEtablissement, Utilisateur)
        .join(Utilisateur, Utilisateur.id == MembreEtablissement.utilisateur_id)
        .where(MembreEtablissement.institution_id == institution.id)
        .order_by(Utilisateur.nom, MembreEtablissement.id)
    ).all()
    assignables = roles_assignables(role_acteur, administrateur_global)
    membres = []
    for membre, personne in paires:
        membres.append({
            "membre": membre,
            "utilisateur": personne,
            "peut_modifier": peut_gerer_role(role_acteur, membre.role, administrateur_global),
        })
    return templates.TemplateResponse(
        request,
        "gestion_etablissement_membres.html",
        {
            "utilisateur": utilisateur,
            "institution": institution,
            "membres": membres,
            "roles_labels": ROLE_MEMBRE_LABELS,
            "roles_assignables": assignables,
            "erreur": erreur,
            "administrateur_global": administrateur_global,
            "total_membres": len(membres),
        },
        headers={"Cache-Control": "no-store, private", "Pragma": "no-cache", "X-Robots-Tag": "noindex, nofollow"},
    )


def _trouver_compte_membre(session: Session, identifiant: str) -> Utilisateur | None:
    valeur = (identifiant or "").strip()
    if not valeur or len(valeur) > 160:
        return None
    compte = session.exec(
        select(Utilisateur).where(Utilisateur.identifiant_connexion == valeur)
    ).first()
    if compte:
        return compte
    try:
        telephone = normaliser_telephone(valeur)
    except TelephoneInvalide:
        return None
    return session.exec(select(Utilisateur).where(Utilisateur.telephone == telephone)).first()


def _role_membre_valide(role: str, compte: Utilisateur) -> bool:
    if role not in ROLE_MEMBRE_LABELS:
        return False
    if role == RoleMembreEtablissement.ENSEIGNANT.value:
        return compte.role == RoleUtilisateur.PROFESSEUR
    return True


@router.get("/etablissements/{institution_id}/gestion")
def page_gestion_etablissement(
    request: Request,
    institution_id: int,
    session: Session = Depends(get_session),
):
    try:
        utilisateur, institution, role_acteur, administrateur_global = _contexte_gestion_institution(
            request, session, institution_id
        )
    except HTTPException as exc:
        if exc.status_code == 401:
            return RedirectResponse("/connexion", status_code=303)
        raise
    return _page_gestion_membres(
        request, session, utilisateur, institution, role_acteur, administrateur_global
    )


@router.post("/etablissements/{institution_id}/membres")
def ajouter_membre_etablissement(
    request: Request,
    institution_id: int,
    identifiant: str = Form(...),
    role: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    try:
        utilisateur, institution, role_acteur, administrateur_global = _contexte_gestion_institution(
            request, session, institution_id
        )
    except HTTPException as exc:
        if exc.status_code == 401:
            return RedirectResponse("/connexion", status_code=303)
        raise
    compte = _trouver_compte_membre(session, identifiant)
    assignables = roles_assignables(role_acteur, administrateur_global)
    if not compte:
        return _page_gestion_membres(
            request, session, utilisateur, institution, role_acteur, administrateur_global,
            "Aucun compte trouvé. Vérifie le téléphone ou l'identifiant institutionnel.",
        )
    if role not in assignables:
        raise HTTPException(status_code=403, detail="Tu ne peux pas attribuer ce rôle.")
    if compte.banni or (compte.role == RoleUtilisateur.ADMIN and not administrateur_global):
        raise HTTPException(status_code=403, detail="Ce compte ne peut pas être ajouté par cet acteur.")
    if not _role_membre_valide(role, compte):
        return _page_gestion_membres(
            request, session, utilisateur, institution, role_acteur, administrateur_global,
            "Pour attribuer le rôle Enseignant, le compte doit déjà avoir le rôle professeur validé par MITARIDALA.",
        )

    existant = session.exec(
        select(MembreEtablissement).where(
            MembreEtablissement.institution_id == institution.id,
            MembreEtablissement.utilisateur_id == compte.id,
        )
    ).first()
    if existant and not peut_gerer_role(role_acteur, existant.role, administrateur_global):
        raise HTTPException(status_code=403, detail="Tu ne peux pas modifier un membre de rang égal ou supérieur.")
    maintenant = datetime.utcnow()
    if existant:
        existant.role = role
        existant.statut = StatutMembreEtablissement.ACTIF.value
        existant.date_modification = maintenant
        existant.modifie_par_id = utilisateur.id
        session.add(existant)
    else:
        session.add(MembreEtablissement(
            institution_id=institution.id,
            utilisateur_id=compte.id,
            role=role,
            statut=StatutMembreEtablissement.ACTIF.value,
            cree_par_id=utilisateur.id,
            modifie_par_id=utilisateur.id,
            date_creation=maintenant,
            date_modification=maintenant,
        ))
    # Champ historique conservé comme établissement principal lorsqu'il est vide.
    # Les appartenances multiples sont portées exclusivement par MembreEtablissement.
    if compte.institution_id is None:
        compte.institution_id = institution.id
        session.add(compte)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return _page_gestion_membres(
            request, session, utilisateur, institution, role_acteur, administrateur_global,
            "L'appartenance n'a pas pu être enregistrée. Actualise la page puis réessaie.",
        )
    return RedirectResponse(
        f"/etablissements/{institution.id}/gestion?ok=membre_ajoute",
        status_code=303,
    )


@router.post("/etablissements/{institution_id}/membres/{membre_id}/role")
def modifier_role_membre_etablissement(
    request: Request,
    institution_id: int,
    membre_id: int,
    role: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur, institution, role_acteur, administrateur_global = _contexte_gestion_institution(
        request, session, institution_id
    )
    membre = session.get(MembreEtablissement, membre_id)
    if not membre or membre.institution_id != institution.id:
        raise HTTPException(status_code=404, detail="Membre introuvable.")
    if not peut_gerer_role(role_acteur, membre.role, administrateur_global):
        raise HTTPException(status_code=403, detail="Tu ne peux pas modifier ce membre.")
    if role not in roles_assignables(role_acteur, administrateur_global):
        raise HTTPException(status_code=403, detail="Tu ne peux pas attribuer ce rôle.")
    compte = session.get(Utilisateur, membre.utilisateur_id)
    if not compte or not _role_membre_valide(role, compte):
        raise HTTPException(status_code=422, detail="Le compte ne remplit pas les conditions de ce rôle.")
    membre.role = role
    membre.date_modification = datetime.utcnow()
    membre.modifie_par_id = utilisateur.id
    session.add(membre)
    session.commit()
    return RedirectResponse(f"/etablissements/{institution.id}/gestion?ok=role_modifie", status_code=303)


@router.post("/etablissements/{institution_id}/membres/{membre_id}/statut")
def modifier_statut_membre_etablissement(
    request: Request,
    institution_id: int,
    membre_id: int,
    statut: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur, institution, role_acteur, administrateur_global = _contexte_gestion_institution(
        request, session, institution_id
    )
    membre = session.get(MembreEtablissement, membre_id)
    if not membre or membre.institution_id != institution.id:
        raise HTTPException(status_code=404, detail="Membre introuvable.")
    if not peut_gerer_role(role_acteur, membre.role, administrateur_global):
        raise HTTPException(status_code=403, detail="Tu ne peux pas modifier ce membre.")
    if membre.utilisateur_id == utilisateur.id:
        raise HTTPException(status_code=403, detail="Tu ne peux pas suspendre ta propre appartenance.")
    if statut not in {item.value for item in StatutMembreEtablissement}:
        raise HTTPException(status_code=422, detail="Statut invalide.")
    membre.statut = statut
    membre.date_modification = datetime.utcnow()
    session.add(membre)
    session.commit()
    return RedirectResponse(f"/etablissements/{institution.id}/gestion?ok=statut_modifie", status_code=303)
