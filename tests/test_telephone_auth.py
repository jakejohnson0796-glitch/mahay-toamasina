import pytest

from app.telephone import TelephoneInvalide, normaliser_telephone


def test_nouveau_format_dix_chiffres_apres_plus_261():
    assert normaliser_telephone("+261 034 12 345 67") == "0341234567"


def test_ancien_format_international_reste_compatible():
    assert normaliser_telephone("+261 34 12 345 67") == "0341234567"


def test_format_local_reste_compatible():
    assert normaliser_telephone("034 12 345 67") == "0341234567"


@pytest.mark.parametrize(
    "telephone",
    [
        "+261 034 12 345 6",
        "+261 034 12 345 678",
        "+261 034 AB 345 67",
        "+261 024 12 345 67",
    ],
)
def test_format_telephone_invalide_rejete(telephone):
    with pytest.raises(TelephoneInvalide):
        normaliser_telephone(telephone)
