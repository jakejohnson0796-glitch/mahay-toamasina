from pathlib import Path

from jinja2 import Environment, FileSystemLoader


ROOT = Path(__file__).resolve().parents[1]


def lire(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_inscription_commence_par_une_selection_explicite_du_profil():
    template = lire("app/templates/register.html")
    choix = template.index('id="bloc-choix-profil"')
    compte = template.index('<p class="auth-section-title">2. Votre compte</p>')

    assert choix < compte
    assert 'Quel profil veux-tu créer ?' in template
    assert 'À qui s’adresse ce compte ?' in template
    assert 'name="role" value="etudiant" required' in template
    assert 'name="role" value="professeur" required' in template
    assert 'name="role" value="repetiteur" required' in template
    assert 'name="role" value="sponsor" required' in template
    assert 'Élève / étudiant(e)' in template
    assert 'Professeur / enseignant(e)' in template
    assert 'Répétiteur / répétitrice' in template
    assert 'Sponsor / partenaire' in template
    # Aucun profil ne doit être présélectionné silencieusement.
    assert 'name="role" value="etudiant" checked' not in template
    assert 'value="etudiant" selected' not in template


def test_les_profils_soumis_a_validation_restent_clairement_identifies():
    template = lire("app/templates/register.html")
    route = lire("app/routers/auth_router.py")
    assert "validation-profils-aide" in template
    assert "avant l’accès à l’espace correspondant" in template
    assert 'statut_verification_enseignant=("en_attente" if est_demande_enseignant else "non_concerne")' in route
    assert 'statut_verification_repetiteur=("en_attente" if est_demande_repetiteur else "non_concerne")' in route
    assert 'statut_verification_sponsor=("en_attente" if est_demande_sponsor else "non_concerne")' in route
    assert "profil_validation_requise(utilisateur)" in route


def test_choix_profil_synchronise_les_champs_academiques_et_la_progression():
    template = lire("app/templates/register.html")
    ui = lire("app/static/js/auth-ui.js")
    scolaire = lire("app/static/js/cascade-scolaire.js")

    assert 'id="role" class="auth-profile-sync"' in template
    assert 'roleSelect.value = option.value' in ui
    assert 'roleSelect.dispatchEvent(new Event("change", { bubbles: true }))' in ui
    assert 'const profile = document.getElementById("role")' in scolaire
    assert 'data-step="4"' in template
    assert "setEtapeActive(4)" in ui
    assert "profilChoisi()" in ui


def test_parent_responsable_reste_un_parcours_distinct_et_valide():
    template = lire("app/templates/register.html")
    ui = lire("app/static/js/auth-ui.js")
    route = lire("app/routers/auth_router.py")

    assert 'id="mode_responsable"' in template
    assert 'modeResponsable.addEventListener("change", actualiser)' in ui
    assert 'roleField.hidden = estResponsable' in ui
    assert 'if (est_responsable)' in route
    assert 'profil_demande = "responsable"' in route


def test_template_inscription_compile():
    env = Environment(loader=FileSystemLoader(ROOT / "app" / "templates"))
    assert env.get_template("register.html") is not None
