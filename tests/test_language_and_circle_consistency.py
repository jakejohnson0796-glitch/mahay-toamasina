"""Regression tests for accessible language choice and circle referential consistency."""

import unittest
from pathlib import Path

from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy.pool import StaticPool

from app.models import (
    CercleEtude,
    Domaine,
    Faculte,
    Filiere,
    Mention,
    ProgrammeUniversitaire,
    RoleUtilisateur,
    Universite,
    Utilisateur,
)
from app.referentiel_academique import (
    profil_correspond_au_cercle,
    type_cercle,
)
from app.routers.academique_router import lister_parcours_nationaux

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app" / "templates" / "base.html"
SIDEBAR_CSS = ROOT / "app" / "static" / "sidebar.css"
LANGUAGE_JS = ROOT / "app" / "static" / "js" / "choix-langue.js"
CIRCLES_TEMPLATE = ROOT / "app" / "templates" / "cercles_list.html"
CIRCLES_ROUTER = ROOT / "app" / "routers" / "cercles_router.py"
ACADEMIC_ROUTER = ROOT / "app" / "routers" / "academique_router.py"


class TestLanguagePickerUI(unittest.TestCase):
    def test_segmented_language_control_keeps_existing_translation_contract(self):
        base = BASE.read_text(encoding="utf-8")
        self.assertIn('id="select-langue"', base)
        self.assertIn('data-langue-choix="fr"', base)
        self.assertIn('data-langue-choix="mg"', base)
        self.assertIn('aria-pressed="true"', base)
        self.assertIn('aria-pressed="false"', base)
        self.assertIn('/static/js/langue.js', base)
        self.assertIn('/static/js/choix-langue.js', base)
        self.assertLess(base.index('/static/js/langue.js'), base.index('/static/js/choix-langue.js'))
        self.assertIn('hidden>', base)

    def test_language_picker_has_keyboard_focus_and_compact_sidebar_states(self):
        css = SIDEBAR_CSS.read_text(encoding="utf-8")
        self.assertIn(".tb-sidebar-langue-option:focus-visible", css)
        self.assertIn('body.sidebar-compact .tb-sidebar-langue-texte', css)
        self.assertIn("@media (max-width: 900px)", css)
        self.assertIn("@media (prefers-reduced-motion: reduce)", css)

    def test_language_buttons_drive_the_existing_select_change_event(self):
        js = LANGUAGE_JS.read_text(encoding="utf-8")
        self.assertIn('document.getElementById("select-langue")', js)
        self.assertIn('bouton.dataset.langueChoix', js)
        self.assertIn('select.dispatchEvent(new Event("change"', js)
        self.assertIn('bouton.setAttribute("aria-pressed"', js)


class TestCircleReferentialConsistency(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            self.universite = Universite(nom="Université Tests Cercles A")
            session.add(self.universite)
            session.commit()
            session.refresh(self.universite)

            self.faculte = Faculte(
                nom="Composante Tests Cercles A",
                universite_id=self.universite.id,
            )
            session.add(self.faculte)
            session.commit()
            session.refresh(self.faculte)

            self.domaine = Domaine(nom="Sciences et gestion tests")
            session.add(self.domaine)
            session.commit()
            session.refresh(self.domaine)

            self.mention = Mention(
                nom="Gestion tests",
                domaine_id=self.domaine.id,
                est_active=True,
            )
            session.add(self.mention)
            session.commit()
            session.refresh(self.mention)

            self.filiere = Filiere(
                nom="Finance tests",
                faculte_id=self.faculte.id,
                mention_id=self.mention.id,
                niveau="L3",
            )
            session.add(self.filiere)
            session.commit()
            session.refresh(self.filiere)

            self.offre = ProgrammeUniversitaire(
                universite_id=self.universite.id,
                filiere_id=self.filiere.id,
                est_active=True,
            )
            session.add(self.offre)

            self.utilisateur = Utilisateur(
                nom="Étudiant Tests Cercles",
                telephone="0340000311",
                mot_de_passe_hash="hash-test",
                role=RoleUtilisateur.ETUDIANT,
                universite_id=self.universite.id,
                faculte_id=self.faculte.id,
                mention_id=self.mention.id,
                filiere_id=self.filiere.id,
                niveau="L3",
            )
            session.add(self.utilisateur)
            session.commit()
            session.refresh(self.utilisateur)

            self.cercle = CercleEtude(
                nom="Finance L3 tests",
                createur_id=self.utilisateur.id,
                mention_id=self.mention.id,
                filiere_id=self.filiere.id,
                niveau="L3",
            )
            session.add(self.cercle)
            session.commit()
            session.refresh(self.cercle)

            self.mention_id = self.mention.id
            self.universite_id = self.universite.id
            self.faculte_id = self.faculte.id
            self.filiere_id = self.filiere.id
            self.utilisateur_id = self.utilisateur.id
            self.cercle_id = self.cercle.id

    def tearDown(self):
        SQLModel.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_active_and_coherent_national_pathway_is_classified(self):
        with Session(self.engine) as session:
            circle = session.get(CercleEtude, self.cercle_id)
            self.assertEqual(type_cercle(circle, session), "parcours")
            user = session.get(Utilisateur, self.utilisateur_id)
            self.assertTrue(profil_correspond_au_cercle(user, circle, session))

    def test_circle_with_a_different_mention_from_its_pathway_is_incomplete(self):
        with Session(self.engine) as session:
            autre = Mention(nom="Droit tests", est_active=True)
            session.add(autre)
            session.commit()
            session.refresh(autre)
            circle = CercleEtude(
                nom="Mention contredite tests",
                createur_id=self.utilisateur_id,
                mention_id=autre.id,
                filiere_id=self.filiere_id,
                niveau="L3",
            )
            session.add(circle)
            session.commit()
            session.refresh(circle)
            self.assertEqual(type_cercle(circle, session), "incomplet")
            user = session.get(Utilisateur, self.utilisateur_id)
            self.assertFalse(profil_correspond_au_cercle(user, circle, session))

    def test_circle_level_must_match_the_official_pathway_level(self):
        with Session(self.engine) as session:
            circle = CercleEtude(
                nom="Niveau contredit tests",
                createur_id=self.utilisateur_id,
                mention_id=self.mention_id,
                filiere_id=self.filiere_id,
                niveau="M1",
            )
            session.add(circle)
            session.commit()
            session.refresh(circle)
            self.assertEqual(type_cercle(circle, session), "incomplet")

    def test_archived_or_inactive_offering_does_not_validate_a_national_circle(self):
        with Session(self.engine) as session:
            offering = session.get(ProgrammeUniversitaire, self.offre.id)
            offering.est_active = False
            session.add(offering)
            session.commit()
            circle = session.get(CercleEtude, self.cercle_id)
            self.assertEqual(type_cercle(circle, session), "incomplet")

    def test_legacy_circle_derives_its_mention_from_its_pathway(self):
        with Session(self.engine) as session:
            circle = CercleEtude(
                nom="Cercle historique tests",
                createur_id=self.utilisateur_id,
                mention_id=None,
                filiere_id=self.filiere_id,
                niveau="L3",
            )
            session.add(circle)
            session.commit()
            session.refresh(circle)
            self.assertEqual(type_cercle(circle, session), "parcours")
            user = session.get(Utilisateur, self.utilisateur_id)
            self.assertTrue(profil_correspond_au_cercle(user, circle, session))

    def test_national_pathway_api_excludes_offers_linked_to_another_university(self):
        with Session(self.engine) as session:
            other_university = Universite(nom="Université Tests Cercles B")
            session.add(other_university)
            session.commit()
            session.refresh(other_university)
            other_faculty = Faculte(
                nom="Composante Tests Cercles B",
                universite_id=other_university.id,
            )
            session.add(other_faculty)
            session.commit()
            session.refresh(other_faculty)
            invalid_cross_offer = Filiere(
                nom="Parcours croisé invalide",
                faculte_id=other_faculty.id,
                mention_id=self.mention_id,
                niveau="L3",
            )
            session.add(invalid_cross_offer)
            session.commit()
            session.refresh(invalid_cross_offer)
            # Erreur référentielle : programme attribué à l'université A,
            # alors que le parcours appartient à une composante de B.
            session.add(ProgrammeUniversitaire(
                universite_id=self.universite_id,
                filiere_id=invalid_cross_offer.id,
                est_active=True,
            ))
            session.commit()

            resultat = lister_parcours_nationaux(
                self.mention_id, "L3", session
            )
            noms = {row["nom"] for row in resultat}
            self.assertIn("Finance tests", noms)
            self.assertNotIn("Parcours croisé invalide", noms)

    def test_national_pathway_api_rejects_unknown_levels_instead_of_falling_back(self):
        with Session(self.engine) as session:
            resultat = lister_parcours_nationaux(
                self.mention_id, "L9", session
            )
            self.assertEqual(resultat, [])

    def test_creation_rejects_a_submitted_mention_that_contradicts_the_pathway(self):
        router = CIRCLES_ROUTER.read_text(encoding="utf-8")
        self.assertIn('erreur=parcours_mention_incoherente', router)
        template = CIRCLES_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn('request.query_params.get("erreur") == "parcours_mention_incoherente"', template)

    def test_circle_cards_show_human_readable_type_and_explicit_inconsistency(self):
        template = CIRCLES_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("Cercle de parcours", template)
        self.assertIn("Tronc commun", template)
        self.assertIn("Groupe libre", template)
        self.assertIn("Référentiel à vérifier", template)
        self.assertIn('erreur=cercle_referentiel_incoherent', template)

    def test_national_pathway_api_uses_component_university_as_the_offer_scope(self):
        api = ACADEMIC_ROUTER.read_text(encoding="utf-8")
        self.assertIn("Faculte.universite_id == ProgrammeUniversitaire.universite_id", api)
        self.assertIn("niveau is not None and niveau not in NIVEAUX", api)


if __name__ == "__main__":
    unittest.main()
