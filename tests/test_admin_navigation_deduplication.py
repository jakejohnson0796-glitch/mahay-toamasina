from pathlib import Path
import re


TEMPLATE = Path(__file__).resolve().parents[1] / "app" / "templates" / "admin_index.html"


def test_admin_landing_has_no_repeated_static_navigation_destinations():
    source = TEMPLATE.read_text(encoding="utf-8")
    destinations = re.findall(r'href=["\']([^"\']+)["\']', source)
    counts = {destination: destinations.count(destination) for destination in set(destinations)}
    duplicates = {destination: count for destination, count in counts.items() if count > 1}

    assert duplicates == {}


def test_admin_landing_keeps_complementary_shortcuts_and_single_harmonization_entry():
    source = TEMPLATE.read_text(encoding="utf-8")

    for destination in (
        "#nouveaux-arrivants",
        "/admin/opportunites",
        "/admin/diagnostics",
        "/admin/securite",
        "/admin/harmonisation-cours",
    ):
        assert source.count(f'href="{destination}"') == 1
