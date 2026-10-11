"""Regression tests for language-navigation placement and circle hierarchy consistency."""

import unittest
from pathlib import Path

from sqlalchemy import event
from sqlmodel import SQLModel, Session, create_engine, select

from app.models import (
    CercleEtude,
    Faculte,
    Filiere,
    Mention,
    ProgrammeUniversitaire,
    RoleUtilisateur,
    Universite,
    Utilisateur,
)
from app.referentiel_academique import (
    cercle_est_national,
    condition_cercles_disponibles,
    filiere_canonique_pour_cercle,
    profil_correspond_au_cercle,
    type_cercle,
)
from app.routers.academique_router import lister_parcours_nationaux

ROOT = Path(__file__).resolve().parents[1]


def nouvel_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def activer_fk(connexion, _record):
        connexion.execute("PRAGMA foreign_keys=ON")

    SQLModel.metadata.create_all(engine)
    return engine


class TestCircleHierarchyConsistency(unittest.TestCase):
    def setUp(self):
        self.engine = nouvel_engine()
        with Session(self.engine) as session:
            self.universite = Universite(nom="Université test active")
            session.add(self.universite)
            session.commit()
            session.refresh(self.universite)

            self.faculte = Faculte(nom="Composante test", universite_id=self.universite.id)
            session.add(self.faculte)
            session.commit()
            session.refresh(self.faculte)

            self.mention = Mention(nom="Gestion test")
            self.autre_mention = Mention(nom="Droit test")
            session.add(self.mention)
            session.add(self.autre_mention)
            session.commit()
            session.refresh(self.mention)
            session.refresh(self.autre_mention)

            self.parcours_l3 = Filiere(
                nom="Comptabilité test",
                faculte_id=self.faculte.id,
                mention_id=self.mention.id,
                niveau="L3",
            )
            self.parcours_l2 = Filiere(
                nom="Comptabilité test",
                faculte_id=self.faculte.id,
                mention_id=self.mention.id,
                niveau="L2",
            )
            session.add(self.parcours_l3)
            session.add(self.parcours_l2)
            session.commit()
            session.refresh(self.parcours_l3)
            session.refresh(self.parcours_l2)

            self.etudiant = Utilisateur(
                nom="Étudiant test",
                telephone="0347000101",
                mot_de_passe_hash="test",
                role=RoleUtilisateur.ETUDIANT,
                universite_id=self.universite.id,
                faculte_id=self.faculte.id,
                mention_id=self.mention.id,
                filiere_id=self.parcours_l3.id,
                niveau="L3",
            )
            session.add(self.etudiant)
            session.commit()
            session.refresh(self.etudiant)

    def tearDown(self):
        self.engine.dispose()

    def test_legacy_circle_infers_mention_and_level_from_its_path(self):
        with Session(self.engine) as session:
            path = session.get(Filiere, self.parcours_l3.id)
            cercle = CercleEtude(
                nom="Cercle historique L3",
                createur_id=self.etudiant.id,
                filiere_id=path.id,
                mention_id=None,
                niveau=None,
            )
            session.add(cercle)
            session.commit()

            self.assertEqual(type_cercle(cercle, path), "parcours")
            self.assertTrue(cercle_est_national(cercle, path))
            self.assertTrue(profil_correspond_au_cercle(self.etudiant, cercle, session))

    def test_explicit_conflict_between_circle_mention_and_path_is_not_hidden(self):
        with Session(self.engine) as session:
            path = session.get(Filiere, self.parcours_l3.id)
            cercle = CercleEtude(
                nom="Cercle incohérent",
                createur_id=self.etudiant.id,
                filiere_id=path.id,
                mention_id=self.autre_mention.id,
                niveau="L3",
            )
            self.assertEqual(type_cercle(cercle, path), "incomplet")
            self.assertFalse(profil_correspond_au_cercle(self.etudiant, cercle, session))

    def test_canonical_path_never_chooses_a_different_level(self):
        with Session(self.engine) as session:
            path_l2 = session.get(Filiere, self.parcours_l2.id)
            canonical = filiere_canonique_pour_cercle(session, path_l2, "L3")
            self.assertEqual(canonical.niveau, "L3")
            self.assertEqual(canonical.id, self.parcours_l3.id)

    def test_available_filter_includes_valid_legacy_circle_from_path_metadata(self):
        with Session(self.engine) as session:
            path = session.get(Filiere, self.parcours_l3.id)
            cercle = CercleEtude(
                nom="Cercle historique disponible",
                createur_id=self.etudiant.id,
                filiere_id=path.id,
                mention_id=None,
                niveau=None,
            )
            session.add(cercle)
            session.commit()
            condition = condition_cercles_disponibles(self.etudiant, session)
            resultats = session.exec(select(CercleEtude).where(condition)).all()
            self.assertIn(cercle.id, {item.id for item in resultats})

    def test_national_path_api_excludes_cross_university_offers_and_other_levels(self):
        with Session(self.engine) as session:
            autre_universite = Universite(nom="Université test autre")
            session.add(autre_universite)
            session.commit()
            session.refresh(autre_universite)
            autre_faculte = Faculte(nom="Autre composante", universite_id=autre_universite.id)
            session.add(autre_faculte)
            session.commit()
            session.refresh(autre_faculte)

            path_hors_offre = Filiere(
                nom="Parcours externe L3",
                faculte_id=autre_faculte.id,
                mention_id=self.mention.id,
                niveau="L3",
            )
            session.add(path_hors_offre)
            session.commit()
            session.refresh(path_hors_offre)

            session.add(ProgrammeUniversitaire(
                universite_id=self.universite.id,
                filiere_id=self.parcours_l3.id,
                est_active=True,
            ))
            # Donnée incohérente historique : une offre rattache le parcours
            # de l'autre université à la mauvaise université.
            session.add(ProgrammeUniversitaire(
                universite_id=self.universite.id,
                filiere_id=path_hors_offre.id,
                est_active=True,
            ))
            session.add(ProgrammeUniversitaire(
                universite_id=self.universite.id,
                filiere_id=self.parcours_l2.id,
                est_active=True,
            ))
            session.commit()

            parcours = lister_parcours_nationaux(self.mention.id, "L3", session)
            ids = {row["id"] for row in parcours}
            self.assertIn(self.parcours_l3.id, ids)
            self.assertNotIn(path_hors_offre.id, ids)
            self.assertNotIn(self.parcours_l2.id, ids)

    def test_inactive_university_cannot_supply_an_active_path(self):
        with Session(self.engine) as session:
            universite = session.get(Universite, self.universite.id)
            universite.est_active = False
            session.add(universite)
            session.commit()
            from app.referentiel_academique import offre_filiere_active_universite
            self.assertFalse(offre_filiere_active_universite(
                session, self.universite.id, self.parcours_l3.id
            ))


class TestLanguageSelectorNavigation(unittest.TestCase):
    def test_selector_is_a_single_sidebar_footer_preference(self):
        base = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
        selector = '<select id="select-langue" name="langue" aria-label="Choisir la langue">'
        self.assertEqual(base.count(selector), 1)
        sidebar_start = base.index('<aside class="tb-sidebar"')
        selector_pos = base.index('<div class="tb-sidebar-langue"')
        sidebar_end = base.index("</aside>", sidebar_start)
        self.assertGreater(selector_pos, sidebar_start)
        self.assertLess(selector_pos, sidebar_end)
        self.assertGreater(selector_pos, base.index('id="bouton-theme"', sidebar_start))
        self.assertNotIn('<option value="mg">Malagasy</option>', base[:selector_pos])

    def test_language_switch_contract_and_compact_sidebar_accessibility_are_preserved(self):
        base = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
        css = (ROOT / "app" / "static" / "sidebar.css").read_text(encoding="utf-8")
        js = (ROOT / "app" / "static" / "js" / "langue.js").read_text(encoding="utf-8")
        self.assertIn('<option value="fr">Français</option>', base)
        self.assertIn('<option value="mg">Malagasy</option>', base)
        self.assertIn('var SELECTEUR = "#select-langue";', js)
        self.assertIn("body.sidebar-compact .tb-sidebar-langue", css)
        self.assertIn(".tb-sidebar-langue select:focus-visible", css)
        self.assertIn("@media (prefers-reduced-motion:reduce)", css)

    def test_circle_creation_contract_rejects_partial_academic_selection(self):
        template = (ROOT / "app" / "templates" / "cercles_list.html").read_text(encoding="utf-8")
        router = (ROOT / "app" / "routers" / "cercles_router.py").read_text(encoding="utf-8")
        js = (ROOT / "app" / "static" / "js" / "cercles-list.js").read_text(encoding="utf-8")
        self.assertIn('data-tronc-mention-id=', template)
        self.assertIn('id="creation-info-tronc-commun" role="status" aria-live="polite" hidden', template)
        self.assertIn('erreur=niveau_requis', router)
        self.assertIn('erreur=combinaison_academique_invalide', router)
        self.assertIn('erreur=incoherence_mention_parcours', router)
        self.assertIn("peutChoisirTroncCommun()", js)
        self.assertIn("formulaire.addEventListener(\"submit\"", js)
        self.assertNotIn('style="display:none;"', template.split('id="creation-info-tronc-commun"', 1)[1].split("</p>", 1)[0])


if __name__ == "__main__":
    unittest.main()
