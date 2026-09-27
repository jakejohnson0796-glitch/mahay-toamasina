import unittest
from types import SimpleNamespace

from app.auth import empreinte_session_utilisateur, session_utilisateur_valide, utilisateur_courant
from app.models import RoleUtilisateur, Utilisateur
from app.rate_limit import limite_depassee


class TestSecurityHardening(unittest.TestCase):
    def test_session_fingerprint_changes_when_password_changes(self):
        utilisateur = Utilisateur(
            id=101,
            nom="Test",
            telephone="0350000101",
            mot_de_passe_hash="hash-a",
            role=RoleUtilisateur.ETUDIANT,
        )
        avant = empreinte_session_utilisateur(utilisateur)
        utilisateur.mot_de_passe_hash = "hash-b"
        apres = empreinte_session_utilisateur(utilisateur)
        self.assertNotEqual(avant, apres)

    def test_old_session_fingerprint_is_rejected_and_cleared(self):
        utilisateur = Utilisateur(
            id=102,
            nom="Test",
            telephone="0350000102",
            mot_de_passe_hash="hash",
            role=RoleUtilisateur.ETUDIANT,
        )
        request = SimpleNamespace(session={
            "user_id": utilisateur.id,
            "auth_fingerprint": "ancienne-session",
        })
        fake_session = SimpleNamespace(get=lambda _model, _id: utilisateur)
        self.assertFalse(session_utilisateur_valide(request.session, utilisateur))
        self.assertIsNone(utilisateur_courant(request, fake_session))
        self.assertEqual(request.session, {})

    def test_rate_limit_blocks_after_threshold(self):
        cle = "security-hardening-test"
        self.assertFalse(limite_depassee(cle, 2, 60))
        self.assertFalse(limite_depassee(cle, 2, 60))
        self.assertTrue(limite_depassee(cle, 2, 60))


if __name__ == "__main__":
    unittest.main()
