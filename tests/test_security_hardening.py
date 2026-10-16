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


def test_strict_csp_garde_unsafe_inline_uniquement_pour_les_attributs_style():
    from app.security_headers import _construire_csp
    csp = _construire_csp("nonce-test-123")
    # MODIF : le compromis demandé autorise unsafe-inline uniquement dans
    # style-src-attr pour KaTeX ; script-src et style-src restent protégés.
    assert "nonce-nonce-test-123" in csp
    assert "script-src-attr 'none'" in csp
    assert "style-src-attr 'unsafe-inline' 'unsafe-hashes'" in csp
    assert "script-src 'self' 'nonce-nonce-test-123' 'strict-dynamic'" in csp
    assert "style-src 'self' 'nonce-nonce-test-123'" in csp
    assert "https://cdn.jsdelivr.net" in csp


def test_email_mfa_keeps_legacy_fingerprint_for_existing_accounts():
    import hashlib

    utilisateur = Utilisateur(
        id=201,
        nom="Test MFA",
        telephone="0340000201",
        mot_de_passe_hash="hash-legacy",
        role=RoleUtilisateur.ETUDIANT,
        email_otp_active=False,
    )
    expected = hashlib.sha256(
        f"{utilisateur.mot_de_passe_hash}|{utilisateur.role.value}|2fa=0".encode("utf-8")
    ).hexdigest()
    assert empreinte_session_utilisateur(utilisateur) == expected

    utilisateur.email_otp_active = True
    assert empreinte_session_utilisateur(utilisateur) != expected


def test_email_otp_is_hashed_expiring_and_single_use():
    from datetime import datetime, timedelta
    from app.auth import hacher_mot_de_passe
    from app.models import CodeEmail2FA
    from app.routers.auth_router import _masquer_email, _verifier_code_email_2fa

    maintenant = datetime.utcnow()
    entree = CodeEmail2FA(
        id=1,
        utilisateur_id=99,
        purpose="connexion",
        code_hash=hacher_mot_de_passe("004261"),
        expire_le=maintenant + timedelta(minutes=10),
    )

    class Resultat:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return self.rows

    class FausseSession:
        def __init__(self, rows):
            self.rows = rows
            self.commits = 0

        def exec(self, _requete):
            return Resultat(self.rows)

        def add(self, _objet):
            pass

        def commit(self):
            self.commits += 1

    session = FausseSession([entree])
    assert _verifier_code_email_2fa(session, 99, "004261", "connexion") is True
    assert entree.utilise is True
    assert session.commits == 1
    assert _verifier_code_email_2fa(session, 99, "004261", "connexion") is False
    assert _verifier_code_email_2fa(session, 99, "004261", "activation") is False
    assert _verifier_code_email_2fa(session, 99, "4261", "connexion") is False
    assert _masquer_email("etudiant@example.com") == "e***@e***.com"


def test_email_otp_rejects_expired_and_mismatched_purpose():
    from datetime import datetime, timedelta
    from app.auth import hacher_mot_de_passe
    from app.models import CodeEmail2FA
    from app.routers.auth_router import _verifier_code_email_2fa

    entree = CodeEmail2FA(
        id=2,
        utilisateur_id=100,
        purpose="activation",
        code_hash=hacher_mot_de_passe("123456"),
        expire_le=datetime.utcnow() - timedelta(seconds=1),
    )

    class Resultat:
        def all(self):
            return [entree]

    class FausseSession:
        def exec(self, _requete):
            return Resultat()

    session = FausseSession()
    assert _verifier_code_email_2fa(session, 100, "123456", "activation") is False
    assert _verifier_code_email_2fa(session, 100, "123456", "connexion") is False
