from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_page_specific_styles_and_notification_script_are_loaded():
    base = read("app/templates/base.html")
    assert 'request.url.path in ["/notifications", "/mes-revisions", "/defis", "/a-propos"]' in base
    assert "feature-pages-refresh.css" in base
    assert 'request.url.path == "/notifications"' in base
    assert "notifications-center.js" in base


def test_notifications_offer_filters_and_search_with_accessible_markup():
    page = read("app/templates/notifications.html")
    script = read("app/static/js/notifications-center.js")
    for token in ('data-notifications-center', 'data-notification-filter="all"',
                  'data-notification-filter="unread"', 'data-notification-filter="read"',
                  'data-notification-search', 'data-notification-card',
                  'data-notification-filter-empty', 'aria-live="polite"'):
        assert token in page
    for token in ('card.hidden = !show', 'setAttribute("aria-pressed"', 'addEventListener("input"'):
        assert token in script
    assert "innerHTML" not in script


def test_notification_labels_and_revision_destinations_are_human_readable():
    router = read("app/routers/notifications_router.py")
    page = read("app/templates/notifications.html")
    assert '"fiche_revision_prete": "Fiche de révision prête"' in router
    assert '"fiche_revision_document_prete": "Fiche de cours disponible"' in router
    assert "item.type_label" in page
    assert 'lien = "/mes-revisions"' in router
    assert 'lien = "/feedback"' in router


def test_revision_sections_keep_navigation_and_mobile_priority_hierarchy():
    page = read("app/templates/mes_revisions.html")
    style = read("app/static/feature-pages-refresh.css")
    assert 'hub-focus-section' in page and 'id="notions-a-revoir"' in page
    assert 'id="progression-par-matiere"' in page
    assert 'id="documents-recents"' in page
    assert 'id="derniers-quiz"' in page
    assert ".page-mes-revisions .mission-entry-strip" in style
    assert "@media(max-width:700px)" in style
    assert "prefers-reduced-motion:reduce" in style


def test_defis_page_has_quick_navigation_and_accessible_progress():
    page = read("app/templates/defis.html")
    assert 'class="gam-jump-nav"' in page
    assert 'id="missions-du-jour"' in page
    assert 'id="badges"' in page
    assert 'id="gagner-xp"' in page
    assert 'role="progressbar"' in page
    assert 'aria-valuenow="{{ progression_xp }}"' in page
    assert "if gamification.xp_prochain else 0" in page


def test_about_page_table_of_contents_links_to_real_sections():
    page = read("app/templates/a_propos.html")
    assert 'class="about-toc"' in page
    for section_id in ("about-mission", "about-parcours", "about-ecosysteme",
                       "about-acces", "about-ia", "about-confiance", "about-communaute"):
        assert f'id="{section_id}"' in page
        assert f'href="#{section_id}"' in page


def test_feature_page_css_has_balanced_braces_and_accessibility_rules():
    css = read("app/static/feature-pages-refresh.css")
    depth = 0
    for char in css:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        assert depth >= 0
    assert depth == 0
    assert "var(--content-surface)" in css
    assert "var(--content-text)" in css
    assert ":focus-visible" in css
    assert "@media(max-width:700px)" in css
    assert "@media(prefers-reduced-motion:reduce)" in css
