from pathlib import Path

from app.ia_transport import REGLES_FORMAT


RACINE = Path(__file__).resolve().parents[1]


def test_renderer_quiz_repare_les_equations_et_integrales_sans_delimiteur():
    source = (RACINE / "app" / "static" / "js" / "rendu_ia.js").read_text(encoding="utf-8")

    assert "function normaliserExpressionsMathematiquesNues(source)" in source
    assert "normaliserExpressionsMathematiquesNues(texte)" in source
    assert r"\b[fg]\s*\(\s*x\s*\)\s*=" in source
    assert r"\\int_\{" in source
    assert r'''return "\\(" + formules[Number(index)] + "\\)"''' in source


def test_renderer_preserve_code_et_formules_deja_delimitees():
    source = (RACINE / "app" / "static" / "js" / "rendu_ia.js").read_text(encoding="utf-8")

    assert "const zonesCodeProtegees" in source
    assert "const zonesMathProtegees" in source
    assert r"\\\[" in source
    assert r"\\\(" in source
    assert r"\x60\x60\x60" in source
    assert "rendreLatexNu(cible)" in source


def test_contrat_ia_exige_les_delimiteurs_maths_dans_les_qcm():
    assert "OBLIGATOIRE : chaque équation, puissance, fraction, intégrale" in REGLES_FORMAT
    assert r"« \(f(x)=3x^{2}+2x-5\) »" in REGLES_FORMAT
    assert r"« \(\displaystyle\int_{0}^{2}(x+1)\,dx\) »" in REGLES_FORMAT
    assert "Un symbole simple peut être écrit directement en Unicode" in REGLES_FORMAT
    assert r"(ex. \frac devient \\frac dans le JSON)" in REGLES_FORMAT

def test_renderer_recupere_les_fractions_des_anciens_quiz_corrompus():
    source = (RACINE / "app" / "static" / "js" / "rendu_ia.js").read_text(encoding="utf-8")

    assert r'.replace(/\u000Crac\b/g, "\\frac")' in source
    assert r'.replace(/\text(?=\s*\{)/g, "\\text")' in source
    assert r"/\(\s*(?:\\?displaystyle\s+)?(\\(?:frac|dfrac|tfrac)" in source
    assert r"/\\(?:frac|dfrac|tfrac)" in source


def test_renderer_repare_les_controles_latex_sans_toucher_au_code():
    source = (RACINE / "app" / "static" / "js" / "rendu_ia.js").read_text(encoding="utf-8")

    assert "const zonesCodeProtegees" in source
    assert "const zonesMathProtegees" in source
    assert r'.replace(/\nabla\b/g, "\\nabla")' in source
    assert r'.replace(/\rho\b/g, "\\rho")' in source
    assert "les formules délimitées seront protégées après réparation" in source


def test_contrat_anticipe_les_collisions_de_symboles_par_discipline():
    assert "le sens d'un symbole dépend de la matière et du contexte" in REGLES_FORMAT
    assert r"\\Delta et \\delta" in REGLES_FORMAT
    assert r"\\Omega et \\omega" in REGLES_FORMAT
    assert "Co n'est pas CO" in REGLES_FORMAT
    assert "unités composées et dimensions" in REGLES_FORMAT
    assert "`<=`, `!=`" in REGLES_FORMAT
    assert "Ar et MGA" in REGLES_FORMAT
    assert "Ne fais aucune substitution globale" in REGLES_FORMAT


def test_quiz_et_tuteur_gardent_un_rendu_independant_pour_chaque_bloc():
    quiz = (RACINE / "app" / "templates" / "quiz_passer.html").read_text(encoding="utf-8")
    resultat = (RACINE / "app" / "templates" / "quiz_resultat.html").read_text(encoding="utf-8")
    moderation = (RACINE / "app" / "templates" / "admin_moderation_quiz.html").read_text(encoding="utf-8")
    tuteur = (RACINE / "app" / "templates" / "tuteur_reponse.html").read_text(encoding="utf-8")

    # Les options restent quatre éléments accessibles et sélectionnables, pas un bloc A/B/C/D aplati.
    assert '{% for choix in item.choix %}' in quiz
    assert '<label class="quiz-choice">' in quiz
    assert 'value="{{ loop.index0 }}"' in quiz
    assert '<span class="quiz-choice-letter">' in quiz
    assert '<span class="quiz-choice-text" data-rendu data-rendu-ligne>{{ choix }}</span>' in quiz

    # La correction et la modération rendent aussi chaque valeur brute séparément.
    assert '<span data-rendu data-rendu-ligne>{{ choix }}</span>' in resultat
    assert '<span data-rendu data-rendu-ligne>{{ s.question.choix[s.question.index_bonne_reponse]' in moderation
    assert 'data-tuteur-content="explication" data-rendu' in tuteur
    assert 'data-tuteur-content="exemple" data-rendu' in tuteur
    assert 'data-tuteur-content="exercice" data-rendu' in tuteur
    assert 'data-tuteur-content="correction" data-rendu' in tuteur



def test_renderer_anticipe_les_commandes_latex_perdues_et_les_parentheses_mathematiques():
    js = (RACINE / "app" / "static" / "js" / "rendu_ia.js").read_text(encoding="utf-8")

    # Exemples vus en production : backslash perdu avant sqrt/approx, et \\t
    # JSON devenu tabulation avant « imes » dans une multiplication.
    assert r".replace(/(^|[^A-Za-z\\])(sqrt|frac|dfrac|tfrac)" in js
    assert r".replace(/([}\d)])(\s*)(approx|times|cdot|pm|leq|geq|neq" in js
    assert r".replace(/\u0009imes(?=\s*(?:\d|[A-Za-z(]))/g" in js
    assert r"normalisee.replace(/\(([^()\n]{1,160})\)/g" in js
    assert "const contientMath =" in js
    assert 'cible.dataset.renduVersion = "7"' in js


def test_renderer_supporte_mhchem_et_formules_chimiques_sans_delimiteurs():
    js = (RACINE / "app" / "static" / "js" / "rendu_ia.js").read_text(encoding="utf-8")

    assert '"ce"' in js
    assert r"/\\ce\{(?:[^{}\n]|\{[^{}\n]*\})*\}/g" in js
    assert "motifReactionChimique" in js
    assert r'"\\ce{" + formuleChimique + "}"' in js
    # Le détecteur exige un indice/coefficient et une flèche pour préserver « Co » vs « CO ».
    assert r"if (!/\d/.test(equation) || !/(?:->|→|⇌|↔)/.test(equation))" in js


def test_renderer_scientifique_est_charge_sur_les_surfaces_ia_et_documents():
    base = (RACINE / "app" / "templates" / "base.html").read_text(encoding="utf-8")

    for route in (
        'request.url.path.startswith("/quiz")',
        'request.url.path.startswith("/tuteur")',
        'request.url.path.startswith("/jeu-cerebral")',
        'request.url.path.startswith("/documents")',
        'request.url.path.startswith("/classe")',
        'request.url.path.startswith("/cercle")',
        'request.url.path.startswith("/moderation")',
        'request.url.path == "/mes-revisions"',
    ):
        assert route in base
    assert base.index("charger-dependances-ia.js") < base.index("rendu_ia.js")
    assert base.count('request.url.path.startswith("/classe")') >= 2
    assert base.count('request.url.path.startswith("/cercle")') >= 2
    assert base.count('request.url.path.startswith("/documents")') >= 2
    assert base.count('href="/static/ai-learning.css') >= 1



def test_contrat_ia_prevoit_les_formules_exactes_qui_ont_pose_probleme():
    contrat = REGLES_FORMAT
    assert r"\(7\times 8+9=65\)" in contrat
    assert r"\(\sqrt{1000}\approx31{,}6\)" in contrat
    assert r"\(\Delta E=\hbar\omega\)" in contrat
    assert r"\(\rho=1\,\mathrm{kg/m^{3}}\)" in contrat
    assert "encadre toute l'expression, et pas seulement l'opérateur" in contrat
    assert "valeur exacte, approximation et arrondi" in contrat
    assert "chiffre des unités" in contrat


def test_rendu_couvre_resumes_documents_et_messages_de_cours():
    documents = (RACINE / "app" / "templates" / "documents_list.html").read_text(encoding="utf-8")
    moderation = (RACINE / "app" / "templates" / "moderation_document_preview.html").read_text(encoding="utf-8")
    messages = (RACINE / "app" / "templates" / "_message_cercle.html").read_text(encoding="utf-8")
    devoir = (RACINE / "app" / "templates" / "classe_devoir.html").read_text(encoding="utf-8")
    salle = (RACINE / "app" / "templates" / "classe_salle.html").read_text(encoding="utf-8")
    moderation_salon = (RACINE / "app" / "templates" / "admin_moderation_salon.html").read_text(encoding="utf-8")

    assert 'class="doc-resume-ia" data-rendu>{{ doc.resume_ia }}</p>' in documents
    assert 'class="doc-resume-ia" data-rendu>{{ doc.resume_ia_mg }}</p>' in documents
    assert '<p data-rendu>{{ document.resume_ia }}</p>' in moderation
    assert '<p data-rendu>{{ document.resume_ia_mg }}</p>' in moderation
    assert 'class="message-contenu" data-rendu data-rendu-ligne' in messages
    assert 'class="thread-apercu-contenu" data-rendu data-rendu-ligne' in messages
    assert 'class="classe-section-card-intro" data-rendu' in devoir
    assert 'contenu.dataset.rendu = ""' in salle
    assert '<span data-rendu data-rendu-ligne>{{ s.message.piece_jointe_nom' in moderation_salon
