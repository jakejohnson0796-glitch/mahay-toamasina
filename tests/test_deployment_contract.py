from scripts.verify_deployment_contract import verifier_contrat_render


def test_render_deployment_contract_is_valid():
    total, minimum = verifier_contrat_render()
    assert total >= minimum
