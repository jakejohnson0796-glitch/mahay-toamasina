"""
Réconciliation canonique du référentiel académique de l'Université de Toamasina.

Le fichier versionné mahay_toamasina_referentiel_source.json est la source
de publication. Cette étape ne devine jamais une offre : elle
1) canonicalise les composantes historiques,
2) fusionne les Filiere strictement équivalentes,
3) active exactement les ProgrammeUniversitaire présents dans la source
   publique,
4) désactive les anciennes offres absentes,
5) conserve les anciennes données seulement lorsqu'elles sont encore
   référencées par des utilisateurs/circles/demandes.

Les cursus institutionnels dont le niveau/parcours détaillé n'est pas
suffisamment documenté restent dans offers_institutionnelles_a_verifier et
ne sont pas publiés dans les sélecteurs ni transformés en cercles.
"""
from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from sqlmodel import Session, select

from .models import (
    CercleEtude,
    DemandeChangementFiliere,
    DemandeCreationCercle,
    Faculte,
    Filiere,
    Mention,
    ProgrammeUniversitaire,
    Universite,
    Utilisateur,
)
from .texte_normalise import normaliser as _normaliser


STATUTS_PUBLICS = {"verifie", "confirme"}

COMPOSANTES_CANONIQUES = {
    "faculte deg": {
        "nom": "Faculté DEG",
        "alias": {
            "faculte deg",
            "droit economie gestion mathematiques et informatique (degmia)",
            "droit economie gestion mathematiques et informatique degmia",
            "faculte de droit, de sciences economiques de gestion et de mathematiques, informatique et applications (fac degmia)",
            "faculte de droit, de sciences economiques, de gestion et de mathematiques, informatique et applications (fac degmia)",
            "faculte de droit des sciences economiques de gestion et de mathematiques informatique et applications (fac degmia)",
            "degmia",
        },
    },
    "faculte des sciences et technologie": {
        "nom": "Faculté des Sciences et Technologie",
        "alias": {
            "faculte des sciences et technologie",
            "sciences et technologies",
            "faculte des sciences et technologies",
        },
    },
    "ecole normale superieure": {
        "nom": "École Normale Supérieure",
        "alias": {
            "ecole normale superieure",
            "ecole normale superieure (ens)",
        },
    },
    "faculte des lettres et sciences humaines": {
        "nom": "Faculté des Lettres et Sciences Humaines",
        "alias": {
            "faculte des lettres et sciences humaines",
            "lettres et sciences humaines",
        },
    },
}


@dataclass
class Rapport:
    composantes_canonicalisees: int = 0
    filieres_fusionnees: int = 0
    filieres_supprimees: int = 0
    offres_activees: int = 0
    offres_desactivees: int = 0
    anciennes_filieres_conservees: int = 0
    mentions_creees: int = 0
    tronc_commun: set[tuple[int, str]] = field(default_factory=set)
    cles_actives: int = 0


def normaliser(texte: str | None) -> str:
    if not texte:
        return ""
    return _normaliser(
        unicodedata.normalize("NFKD", texte)
        .encode("ascii", "ignore")
        .decode("ascii")
    )


def lire_source(chemin: str) -> dict:
    return json.loads(Path(chemin).read_text(encoding="utf-8"))


def _reassigner_mention(session: Session, ancien_id: int, nouveau_id: int) -> None:
    for filiere in session.exec(select(Filiere).where(Filiere.mention_id == ancien_id)).all():
        filiere.mention_id = nouveau_id
        session.add(filiere)
    for utilisateur in session.exec(select(Utilisateur).where(Utilisateur.mention_id == ancien_id)).all():
        utilisateur.mention_id = nouveau_id
        session.add(utilisateur)
    for cercle in session.exec(select(CercleEtude).where(CercleEtude.mention_id == ancien_id)).all():
        cercle.mention_id = nouveau_id
        session.add(cercle)
    for demande in session.exec(
        select(DemandeCreationCercle).where(DemandeCreationCercle.mention_id == ancien_id)
    ).all():
        demande.mention_id = nouveau_id
        session.add(demande)
    for demande in session.exec(
        select(DemandeChangementFiliere).where(DemandeChangementFiliere.nouvelle_mention_id == ancien_id)
    ).all():
        demande.nouvelle_mention_id = nouveau_id
        session.add(demande)


def _reassigner_faculte(session: Session, ancien_id: int, nouveau_id: int) -> None:
    for filiere in session.exec(select(Filiere).where(Filiere.faculte_id == ancien_id)).all():
        filiere.faculte_id = nouveau_id
        session.add(filiere)
    for utilisateur in session.exec(select(Utilisateur).where(Utilisateur.faculte_id == ancien_id)).all():
        utilisateur.faculte_id = nouveau_id
        session.add(utilisateur)
    for demande in session.exec(
        select(DemandeChangementFiliere).where(DemandeChangementFiliere.nouvelle_faculte_id == ancien_id)
    ).all():
        demande.nouvelle_faculte_id = nouveau_id
        session.add(demande)


def _reassigner_filiere(session: Session, ancien_id: int, nouveau_id: int) -> None:
    for programme in session.exec(
        select(ProgrammeUniversitaire).where(ProgrammeUniversitaire.filiere_id == ancien_id)
    ).all():
        # Une seule offre active par (universite, filiere). Si l'offre
        # canonique existe déjà sur le survivant, l'ancienne ligne est
        # simplement désactivée au lieu de créer une collision d'index.
        existe = session.exec(
            select(ProgrammeUniversitaire).where(
                ProgrammeUniversitaire.universite_id == programme.universite_id,
                ProgrammeUniversitaire.filiere_id == nouveau_id,
                ProgrammeUniversitaire.est_active == True,  # noqa: E712
            )
        ).first()
        if existe and programme.est_active:
            programme.est_active = False
        else:
            programme.filiere_id = nouveau_id
        session.add(programme)

    for utilisateur in session.exec(select(Utilisateur).where(Utilisateur.filiere_id == ancien_id)).all():
        utilisateur.filiere_id = nouveau_id
        session.add(utilisateur)

    for cercle in session.exec(select(CercleEtude).where(CercleEtude.filiere_id == ancien_id)).all():
        cercle.filiere_id = nouveau_id
        session.add(cercle)

    for demande in session.exec(
        select(DemandeCreationCercle).where(DemandeCreationCercle.filiere_id == ancien_id)
    ).all():
        demande.filiere_id = nouveau_id
        session.add(demande)

    for demande in session.exec(
        select(DemandeChangementFiliere).where(
            (DemandeChangementFiliere.ancienne_filiere_id == ancien_id)
            | (DemandeChangementFiliere.nouvelle_filiere_id == ancien_id)
        )
    ).all():
        if demande.ancienne_filiere_id == ancien_id:
            demande.ancienne_filiere_id = nouveau_id
        if demande.nouvelle_filiere_id == ancien_id:
            demande.nouvelle_filiere_id = nouveau_id
        session.add(demande)


def _trouver_faculte_canonique(
    session: Session, universite_id: int, nom_source: str, rapport: Rapport
) -> Faculte:
    cle_source = normaliser(nom_source)
    config = COMPOSANTES_CANONIQUES.get(cle_source)
    alias = config["alias"] if config else {cle_source}
    nom_canonique = config["nom"] if config else nom_source

    candidats = [
        f for f in session.exec(select(Faculte).where(Faculte.universite_id == universite_id)).all()
        if normaliser(f.nom) in {normaliser(x) for x in alias | {nom_canonique}}
    ]
    if not candidats:
        faculte = Faculte(nom=nom_canonique, universite_id=universite_id)
        session.add(faculte)
        session.commit()
        session.refresh(faculte)
        return faculte

    faculte = next((f for f in candidats if normaliser(f.nom) == normaliser(nom_canonique)), min(candidats, key=lambda f: f.id))
    doublons = [f for f in candidats if f.id != faculte.id]

    for doublon in doublons:
        _reassigner_faculte(session, doublon.id, faculte.id)
        session.delete(doublon)
        rapport.composantes_canonicalisees += 1

    if faculte.nom != nom_canonique:
        faculte.nom = nom_canonique
        session.add(faculte)
        rapport.composantes_canonicalisees += 1

    session.commit()
    return faculte


def _trouver_mention_canonique(
    session: Session, nom: str, domaine_id: int | None, rapport: Rapport
) -> Mention:
    candidats = [
        m for m in session.exec(select(Mention)).all()
        if normaliser(m.nom) == normaliser(nom)
    ]
    if not candidats:
        mention = Mention(nom=nom, domaine_id=domaine_id)
        session.add(mention)
        session.commit()
        session.refresh(mention)
        rapport.mentions_creees += 1
        return mention

    cible = min(candidats, key=lambda m: m.id)
    for doublon in [m for m in candidats if m.id != cible.id]:
        _reassigner_mention(session, doublon.id, cible.id)
        session.delete(doublon)
    if cible.nom != nom:
        cible.nom = nom
    if cible.domaine_id is None and domaine_id is not None:
        cible.domaine_id = domaine_id
    cible.est_active = True
    session.add(cible)
    session.commit()
    return cible


def _filiere_sans_reference(session: Session, filiere_id: int) -> bool:
    refs = [
        session.exec(select(ProgrammeUniversitaire.id).where(ProgrammeUniversitaire.filiere_id == filiere_id).limit(1)).first(),
        session.exec(select(Utilisateur.id).where(Utilisateur.filiere_id == filiere_id).limit(1)).first(),
        session.exec(select(CercleEtude.id).where(CercleEtude.filiere_id == filiere_id).limit(1)).first(),
        session.exec(select(DemandeCreationCercle.id).where(DemandeCreationCercle.filiere_id == filiere_id).limit(1)).first(),
        session.exec(
            select(DemandeChangementFiliere.id).where(
                (DemandeChangementFiliere.ancienne_filiere_id == filiere_id)
                | (DemandeChangementFiliere.nouvelle_filiere_id == filiere_id)
            ).limit(1)
        ).first(),
    ]
    return not any(x is not None for x in refs)


def _filiere_canonique(
    session: Session,
    faculte_id: int,
    mention_id: int,
    niveau: str,
    nom: str,
    rapport: Rapport,
) -> Filiere:
    candidats = session.exec(
        select(Filiere).where(
            Filiere.faculte_id == faculte_id,
            Filiere.mention_id == mention_id,
            Filiere.niveau == niveau,
        )
    ).all()
    candidats = [f for f in candidats if normaliser(f.nom) == normaliser(nom)]

    if not candidats:
        filiere = Filiere(nom=nom, faculte_id=faculte_id, mention_id=mention_id, niveau=niveau)
        session.add(filiere)
        session.commit()
        session.refresh(filiere)
        return filiere

    cible = min(candidats, key=lambda f: f.id)
    doublons = [f for f in candidats if f.id != cible.id]
    for doublon in doublons:
        _reassigner_filiere(session, doublon.id, cible.id)
        if _filiere_sans_reference(session, doublon.id):
            session.delete(doublon)
            rapport.filieres_supprimees += 1
        else:
            rapport.anciennes_filieres_conservees += 1
        rapport.filieres_fusionnees += 1

    if cible.nom != nom:
        cible.nom = nom
        session.add(cible)
    session.commit()
    return cible


def reconcilier(
    session: Session,
    chemin_source: str,
    dry_run: bool = False,
) -> Rapport:
    data = lire_source(chemin_source)
    lignes = [
        x for x in data.get("formations", [])
        if normaliser(x.get("statut")) in STATUTS_PUBLICS
    ]
    rapport = Rapport()

    universite = session.exec(
        select(Universite).where(Universite.est_active == True)  # noqa: E712
    ).all()
    universite = next((u for u in universite if normaliser(u.nom) == normaliser("Université de Toamasina")), None)
    if not universite:
        return rapport

    # Domaines : réutilise le domaine homonyme existant, sans créer de variantes.
    domaines = {normaliser(d.nom): d for d in session.exec(select(__import__("app.models", fromlist=["Domaine"]).Domaine)).all()}

    cles_desirees: set[tuple[int, int, int, str]] = set()
    cles_tronc: set[tuple[int, str]] = set()
    facultes_scope: set[int] = set()

    for ligne in lignes:
        faculte = _trouver_faculte_canonique(session, universite.id, ligne["composante"], rapport)
        facultes_scope.add(faculte.id)

        dom = None
        cle_dom = normaliser(ligne.get("domaine"))
        if cle_dom:
            dom = domaines.get(cle_dom)
            if dom is None:
                from .models import Domaine
                dom = Domaine(nom=ligne["domaine"])
                session.add(dom)
                session.commit()
                session.refresh(dom)
                domaines[cle_dom] = dom

        mention = _trouver_mention_canonique(session, ligne["mention"], dom.id if dom else None, rapport)
        niveau = ligne.get("niveau") or None
        if not niveau:
            continue

        if normaliser(ligne.get("type")) == normaliser("Tronc commun"):
            cles_tronc.add((mention.id, niveau))
            # Aucun parcours technique ne doit être publié pour un niveau
            # explicitement déclaré en tronc commun.
            for programme in session.exec(
                select(ProgrammeUniversitaire)
                .join(Filiere, Filiere.id == ProgrammeUniversitaire.filiere_id)
                .where(
                    ProgrammeUniversitaire.universite_id == universite.id,
                    ProgrammeUniversitaire.est_active == True,  # noqa: E712
                    Filiere.faculte_id == faculte.id,
                    Filiere.mention_id == mention.id,
                    Filiere.niveau == niveau,
                )
            ).all():
                programme.est_active = False
                session.add(programme)
                rapport.offres_desactivees += 1
            rapport.tronc_commun.add((mention.id, niveau))
            continue

        filiere = _filiere_canonique(
            session, faculte.id, mention.id, niveau, ligne["parcours"], rapport
        )
        cles_desirees.add((faculte.id, mention.id, int(niveau in {"L1","L2","L3","M1","M2"}) and 0 or 0, normaliser(filiere.nom)))
        # The third component above is deliberately not used below; keep
        # exact level in a second canonical key to avoid accidental
        # cross-level merging.
        cle_exacte = (faculte.id, mention.id, niveau, normaliser(filiere.nom))
        cles_desirees.discard((faculte.id, mention.id, 0, normaliser(filiere.nom)))
        cles_desirees.add((faculte.id, mention.id, niveau, normaliser(filiere.nom)))

        offres = session.exec(
            select(ProgrammeUniversitaire).where(
                ProgrammeUniversitaire.universite_id == universite.id,
                ProgrammeUniversitaire.filiere_id == filiere.id,
            )
        ).all()
        actif = next((o for o in offres if o.est_active), None)
        if actif is None:
            if offres:
                cible = min(offres, key=lambda o: o.id)
                cible.est_active = True
                session.add(cible)
            else:
                session.add(
                    ProgrammeUniversitaire(
                        universite_id=universite.id,
                        filiere_id=filiere.id,
                        est_active=True,
                    )
                )
            session.commit()
            rapport.offres_activees += 1
        for extra in offres:
            if actif is not None and extra.id != actif.id and extra.est_active:
                extra.est_active = False
                session.add(extra)

    # Désactive toute offre encore active dans les composantes canonisées qui
    # ne figure plus dans la source publique canonique.
    for programme in session.exec(
        select(ProgrammeUniversitaire).where(
            ProgrammeUniversitaire.universite_id == universite.id,
            ProgrammeUniversitaire.est_active == True,  # noqa: E712
        )
    ).all():
        filiere = session.get(Filiere, programme.filiere_id)
        if not filiere or filiere.faculte_id not in facultes_scope:
            continue
        cle = (
            filiere.faculte_id,
            filiere.mention_id,
            filiere.niveau,
            normaliser(filiere.nom),
        )
        if cle not in cles_desirees:
            programme.est_active = False
            session.add(programme)
            rapport.offres_desactivees += 1

    rapport.cles_actives = len(cles_desirees)
    rapport.tronc_commun |= cles_tronc

    if dry_run:
        session.rollback()
    else:
        session.commit()

    return rapport
