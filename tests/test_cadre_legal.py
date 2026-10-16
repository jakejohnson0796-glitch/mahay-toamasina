from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def lire(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_cadre_legal_public_regroupe_conditions_ethique_confidentialite_et_mentions():
    route = lire("app/routers/legal_router.py")
    template = lire("app/templates/cadre_legal.html")
    assert '@router.get("/cadre-legal"' in route
    assert '@router.get("/conditions-utilisation"' in route
    assert '@router.get("/charte-ethique"' in route
    assert '@router.get("/confidentialite"' in route
    assert '@router.get("/mentions-legales"' in route
    assert "utilisateur_courant" not in route
    for section in (
        'id="conditions"',
        'id="ethique"',
        'id="confidentialite"',
        'id="intelligence-artificielle"',
        'id="moderation"',
        'id="mentions-legales"',
    ):
        assert section in template
    assert "2014-038" in template
    assert "digital.gov.mg" in template


def test_inscription_exige_une_acceptation_expresse_cote_navigateur_et_serveur():
    template = lire("app/templates/register.html")
    route = lire("app/routers/auth_router.py")
    assert 'id="accepter_conditions"' in template
    assert 'name="accepter_conditions"' in template
    assert 'value="oui"' in template
    assert 'required aria-describedby="conditions-aide"' in template
    assert 'href="/cadre-legal#conditions"' in template
    assert 'href="/cadre-legal#ethique"' in template
    assert 'href="/cadre-legal#confidentialite"' in template
    assert 'accepter_conditions: str = Form("")' in route
    garde = route.index('if accepter_conditions != "oui":')
    creation = route.index("utilisateur = Utilisateur(", garde)
    assert garde < creation
    assert "Vous devez lire et accepter les conditions" in route


def test_acceptation_enregistre_une_version_et_un_horodatage_sans_modifier_les_anciens_comptes():
    model = lire("app/models.py")
    migration = lire("alembic/versions/e8d1a6c4f2b9_acceptation_conditions_utilisateur.py")
    route = lire("app/routers/auth_router.py")
    constants = lire("app/conditions_legales.py")
    assert "conditions_acceptees_le: Optional[datetime] = None" in model
    assert "version_conditions_acceptees: Optional[str]" in model
    assert 'down_revision: str | None = "9a4f7d1c2e80"' in migration
    assert 'sa.Column("conditions_acceptees_le", sa.DateTime(), nullable=True)' in migration
    assert 'sa.Column("version_conditions_acceptees", sa.String(length=32), nullable=True)' in migration
    assert "conditions_acceptees_le=datetime.utcnow()" in route
    assert "version_conditions_acceptees=VERSION_CONDITIONS" in route
    assert 'VERSION_CONDITIONS = "1.0"' in constants


def test_page_legale_est_accessible_depuis_le_pied_de_page_et_le_menu():
    base = lire("app/templates/base.html")
    main = lire("app/main.py")
    assert "legal_router" in main
    assert 'href="/cadre-legal"' in base
    assert "static/legal.css" in base
    css = lire("app/static/legal.css")
    assert ".cadre-legal-section" in css
    assert "@media(max-width:640px)" in css
    assert "prefers-reduced-motion" in css


def test_libelles_du_cadre_legal_et_du_consentement_sont_traduits_en_malagasy():
    translations = lire("app/static/js/langue.js")
    for phrase in (
        '"Conditions d’utilisation":',
        '"Charte éthique":',
        '"Confidentialité":',
        '"J’ai lu et j’accepte les":',
        '"Documents à lire avant inscription :":',
        '"Notice de confidentialité":',
        '"Les réponses du Quiz IA et du Tuteur IA sont générées automatiquement.',
        '"Les informations de compte : nom affiché, numéro de téléphone',
    ):
        assert phrase in translations
