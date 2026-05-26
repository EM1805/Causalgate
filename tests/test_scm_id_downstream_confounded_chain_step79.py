from scm_parts.admg import admg_from_edges
from scm_parts.id_canonical_formula import canonical_id_formula_diagnostic
from scm_parts.id_full import full_id
from scm_parts.id_status import id_capability_flags


def _graph():
    return admg_from_edges(
        ["X", "A", "B", "Y"],
        [("X", "A"), ("A", "B"), ("B", "Y")],
        [("X", "B")],
    )


def test_step79_downstream_confounded_chain_has_owned_canonical_formula_authority():
    result = full_id(_graph(), ["X"], ["Y"], max_depth=12).to_dict()

    assert result["identified"] is True
    assert result["primary_formula_authority"] == "id_canonical_formula_step60"
    assert result["canonical_formula_status"] == "identified_canonical_id7_downstream_confounded_chain_carried_q_formula_step79"
    assert result["canonical_id7_carried_q_formula_used"] == 1
    assert "ID-7" in result["canonical_rules"].split("|")
    assert "sum_{A,B}" in result["formula"]
    assert "sum_{X_prime}" in result["formula"]
    assert "P(B | X_prime,A)" in result["formula"]
    assert "P(Y | X,A,B)" in result["formula"]
    assert result["full_id_claim_allowed"] == 1


def test_step79_canonical_formula_family_is_strict_and_does_not_overclaim():
    # Adding an extra bidirected edge changes the family, so the strict Step-79
    # canonical recognizer must not claim this formula even though the delegate
    # may still return a conservative identified/blocked result elsewhere.
    widened = admg_from_edges(
        ["X", "A", "B", "Y"],
        [("X", "A"), ("A", "B"), ("B", "Y")],
        [("X", "B"), ("A", "Y")],
    )
    canonical = canonical_id_formula_diagnostic(widened, ["X"], ["Y"], max_depth=12)

    assert canonical.status != "identified_canonical_id7_downstream_confounded_chain_carried_q_formula_step79"
    assert "CANONICAL_ID7_DOWNSTREAM_CONFOUNDED_CHAIN_CARRIED_Q_FORMULA_STEP79" not in canonical.reason_codes


def test_step79_status_flags_present_without_full_id_claim():
    flags = id_capability_flags()

    assert flags["id_full_downstream_confounded_chain_id7_step79_implemented"] == 1
    assert "downstream_confounded_chain_step79" in flags["id_algorithm_status"]
    assert flags["full_recursive_id_implemented"] == 1
    assert flags["full_id_claim_allowed"] == 1
