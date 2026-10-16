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

        def execute(self, _requete):
            from types import SimpleNamespace
            # Simule l'UPDATE conditionnel gagnant ; la ligne ORM reflète
            # ensuite l'état consommé pour la vérification de rejeu.
            if not entree.utilise:
                entree.utilise = True
                return SimpleNamespace(rowcount=1)
            return SimpleNamespace(rowcount=0)

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



def test_mfa_generation_prevents_old_session_fingerprint_from_reviving():
    from app.auth import empreinte_session_utilisateur

    utilisateur = Utilisateur(
        id=202,
        nom="MFA generation",
        telephone="0340000202",
        mot_de_passe_hash="hash-stable",
        role=RoleUtilisateur.ETUDIANT,
        totp_active=False,
        email_otp_active=False,
        mfa_session_generation=None,
    )
    empreinte_historique = empreinte_session_utilisateur(utilisateur)

    utilisateur.email_otp_active = True
    utilisateur.mfa_session_generation = "generation-activation"
    empreinte_active = empreinte_session_utilisateur(utilisateur)
    assert empreinte_active != empreinte_historique

    utilisateur.email_otp_active = False
    utilisateur.mfa_session_generation = "generation-desactivation"
    empreinte_apres_desactivation = empreinte_session_utilisateur(utilisateur)
    assert empreinte_apres_desactivation != empreinte_historique
    assert empreinte_apres_desactivation != empreinte_active


def test_brevo_https_configures_email_without_smtp(monkeypatch):
    from app import email_utils
    from app.config import parametres

    monkeypatch.setattr(parametres, "brevo_api_key", "cle-api-test")
    monkeypatch.setattr(parametres, "smtp_from_email", "securite@example.org")
    monkeypatch.setattr(parametres, "smtp_hote", "")
    monkeypatch.setattr(parametres, "smtp_utilisateur", "")
    monkeypatch.setattr(parametres, "smtp_mot_de_passe", "")

    assert email_utils.email_configure() is True


def test_brevo_api_sends_transactional_email_over_https_without_smtp(monkeypatch):
    import json
    from app import email_utils
    from app.config import parametres

    monkeypatch.setattr(parametres, "email_transport", "brevo_api")
    monkeypatch.setattr(parametres, "brevo_api_key", "cle-api-test")
    monkeypatch.setattr(parametres, "brevo_sender_name", "Gasy Mahay")
    monkeypatch.setattr(parametres, "smtp_from_email", "securite@example.org")
    monkeypatch.setattr(parametres, "smtp_hote", "")
    monkeypatch.setattr(parametres, "smtp_utilisateur", "")
    monkeypatch.setattr(parametres, "smtp_mot_de_passe", "")
    capture = {}

    class FausseReponse:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"messageId":"test-message"}'

    def faux_urlopen(requete, timeout):
        capture["requete"] = requete
        capture["timeout"] = timeout
        return FausseReponse()

    monkeypatch.setattr(email_utils.urllib.request, "urlopen", faux_urlopen)

    def smtp_interdit(*_args, **_kwargs):
        raise AssertionError("L'API HTTPS doit être utilisée, pas SMTP.")

    monkeypatch.setattr(email_utils.smtplib, "SMTP", smtp_interdit)
    email_utils.envoyer_email(
        "etudiant@example.net",
        "Gasy Mahay — code de connexion",
        "Votre code est 004261.",
    )

    requete = capture["requete"]
    assert requete.full_url == "https://api.brevo.com/v3/smtp/email"
    assert requete.get_method() == "POST"
    assert requete.get_header("Api-key") == "cle-api-test"
    assert capture["timeout"] == 10
    payload = json.loads(requete.data.decode("utf-8"))
    assert payload["sender"] == {
        "name": "Gasy Mahay",
        "email": "securite@example.org",
    }
    assert payload["to"] == [{"email": "etudiant@example.net"}]
    assert payload["textContent"] == "Votre code est 004261."



def test_render_brevo_mode_does_not_report_smtp_only_as_configured(monkeypatch):
    import pytest
    from app import email_utils
    from app.config import parametres

    monkeypatch.setattr(parametres, "email_transport", "brevo_api")
    monkeypatch.setattr(parametres, "brevo_api_key", "")
    monkeypatch.setattr(parametres, "smtp_from_email", "securite@example.org")
    monkeypatch.setattr(parametres, "smtp_hote", "smtp.example.org")
    monkeypatch.setattr(parametres, "smtp_utilisateur", "user")
    monkeypatch.setattr(parametres, "smtp_mot_de_passe", "mot-de-passe-test")

    assert email_utils.email_configure() is False
    with pytest.raises(email_utils.EmailNonConfigure):
        email_utils.envoyer_email("etudiant@example.net", "Test", "Test")

def test_email_not_configured_without_brevo_or_smtp(monkeypatch):
    import pytest
    from app import email_utils
    from app.config import parametres

    monkeypatch.setattr(parametres, "brevo_api_key", "")
    monkeypatch.setattr(parametres, "smtp_from_email", "")
    monkeypatch.setattr(parametres, "smtp_hote", "")
    monkeypatch.setattr(parametres, "smtp_utilisateur", "")
    monkeypatch.setattr(parametres, "smtp_mot_de_passe", "")

    assert email_utils.email_configure() is False
    with pytest.raises(email_utils.EmailNonConfigure):
        email_utils.envoyer_email("etudiant@example.net", "Test", "Test")


if __name__ == "__main__":
    unittest.main()
