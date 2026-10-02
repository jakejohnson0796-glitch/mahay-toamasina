from scripts.verify_migrations import verifier_graphe


def test_alembic_graph_has_single_head_and_complete_chain():
    head, total = verifier_graphe()
    assert head
    assert total >= 1
