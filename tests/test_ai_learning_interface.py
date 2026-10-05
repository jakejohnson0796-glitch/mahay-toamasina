from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def lire(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_base_charge_les_assets_quiz_tuteur_et_renderer_ia():
    # MODIF : vérifie le nouveau pipeline CDN + renderer et son ordre figé.
    base = lire("app/templates/base.html")
    assert 'version_asset(\'ai-learning.css\')' in base
    assert 'version_asset(\'js/rendu_ia.js\')' in base
    assert 'request.url.path.startswith("/quiz")' in base
    assert 'request.url.path.startswith("/tuteur")' in base
    ordre = [
        'katex@0.16.11/dist/katex.min.css',
        'katex@0.16.11/dist/katex.min.js',
        'katex@0.16.11/dist/contrib/mhchem.min.js',
        'marked@12.0.2/marked.min.js',
        'dompurify@3.1.6/dist/purify.min.js',
        'highlightjs/cdn-release@11.10.0/build/highlight.min.js',
        '/static/js/rendu_ia.js',
    ]
    positions = [base.index(item) for item in ordre]
    assert positions == sorted(positions)


def test_pages_quiz_et_tuteur_utilisent_data_rendu_et_n_injectent_pas_de_html_ia():
    # MODIF : les pages ne doivent plus appeler le renderer serveur.
    paths = [
        "app/templates/quiz.html",
        "app/templates/quiz_passer.html",
        "app/templates/quiz_resultat.html",
        "app/templates/quiz_historique.html",
        "app/templates/quiz_reflexion.html",
        "app/templates/tuteur.html",
        "app/templates/tuteur_reponse.html",
        "app/templates/admin_moderation_quiz.html",
    ]
    for path in paths:
        template = lire(path)
        assert "rendre_math_html" not in template, path
        assert "rendre_choix_math_html" not in template, path
        assert "texte_ia" not in template, path
        assert "innerHTML" not in template, path

    assert "data-rendu" in lire("app/templates/quiz_passer.html")
    assert "data-rendu" in lire("app/templates/tuteur_reponse.html")
    assert '<p class="ai-answer-question" data-rendu>{{ session_tuteur.question }}</p>' in lire("app/templates/tuteur_reponse.html")
    tuteur = lire("app/templates/tuteur.html")
    assert 'class="ai-tuteur-history-card"' in tuteur
    assert 'class="ai-tuteur-history-question" data-rendu' in tuteur
    assert 'class="ai-tuteur-history-date"' in tuteur
    assert 'Ouvrir la session' in tuteur
    assert 'class="ai-reflexion-theme" data-rendu' in lire("app/templates/quiz_reflexion.html")


def test_historique_tuteur_est_cliquable_et_lisible():
    css = lire("app/static/ai-learning.css")
    assert ".ai-tuteur-history-card" in css
    assert "cursor: pointer" in css
    assert ".ai-tuteur-history-date" in css
    assert ".ai-tuteur-history-question" in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in css
    assert "@media (max-width: 760px)" in css


def test_interface_quiz_contient_navigation_et_progression():
    quiz = lire("app/templates/quiz_passer.html")
    assert "data-quiz-form" in quiz
    assert "data-quiz-nav" in quiz
    assert "data-quiz-progress-fill" in quiz
    assert "data-quiz-submit" in quiz


def test_interface_tuteur_contient_suggestions_et_compteur():
    tuteur = lire("app/templates/tuteur.html")
    assert "data-tuteur-question" in tuteur
    assert "data-tuteur-count" in tuteur
    assert "data-tuteur-prompt" in tuteur
    assert "data-tuteur-form" in tuteur


def test_css_et_js_dedies_exist():
    assert (ROOT / "app/static/ai-learning.css").exists()
    assert (ROOT / "app/static/js/ai-learning.js").exists()
    # MODIF : nouveaux modules de parsing/rendu obligatoires.
    assert (ROOT / "app/static/js/rendu_ia.js").exists()
    assert (ROOT / "app/json_latex.py").exists()


def test_ai_learning_js_ne_contient_plus_innerhtml_ia():
    # MODIF : le polling Tuteur doit remettre le texte brut au renderer.
    js = lire("app/static/js/ai-learning.js")
    assert "innerHTML" not in js
    assert "rendreReponseIA" in js


def test_tuteur_api_ne_prepare_plus_de_html():
    # MODIF : l'endpoint de statut doit renvoyer le texte brut.
    route = lire("app/routers/tuteur_router.py")
    assert 'filters["texte_ia"]' not in route
    assert 'normaliser_structure_tuteur' in route
    assert '"explication": rendu("explication")' in route
    assert '"correction": rendu("correction")' in route


def test_route_tuteur_persiste_le_statut_de_verification():
    route = lire("app/routers/tuteur_router.py")
    assert 'statut_verification = reponse.pop("_statut_verification", "terminee")' in route
    assert 'statut_verification_ia=statut_verification' in route


def test_tuteur_ne_declare_pas_une_reponse_a_revoir_comme_terminee():
    route = lire("app/routers/tuteur_router.py")
    assert '"_verification_ok"' in lire("app/ai_quiz.py")
    assert '"a_revoir" if' not in route
    template = lire("app/templates/tuteur_reponse.html")
    assert 'statut_verification_ia == "a_revoir"' in template


def test_contrat_tuteur_contient_un_retry_structure():
    code = lire("app/ai_quiz.py")
    assert "for tentative in range(2)" in code
    assert "RAPPEL DE RETRY" in code


def test_tuteur_marque_une_reponse_non_confirmee_sans_la_masquer():
    code = lire("app/ai_quiz.py")
    assert 'if parametres.ai_ensemble_enabled and not verification_ok:' in code
    assert 'reponse_finale["_verification_ok"] = False' in code
    assert '"a_revoir"' in code
    assert 'return reponse_finale' in code


def test_tuteur_ne_devient_pas_vide_quand_la_verification_echoue():
    code = lire("app/ai_quiz.py")
    assert 'reponse_finale["_statut_verification"]' in code
    template = lire("app/templates/tuteur_reponse.html")
    assert "Réponse disponible · vérification à confirmer" in template
    assert "Réponse disponible · vérification momentanément indisponible" in template
