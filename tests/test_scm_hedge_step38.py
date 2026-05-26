from scm_parts.admg import admg_from_edges
from scm_parts.hedge import formal_hedge_diagnostic
from scm_parts.id_algorithm import identify_effect


def test_formal_hedge_certificate_blocks_direct_unobserved_confounding():
    g = admg_from_edges(["X", "Y"], [("X", "Y")], [("X", "Y")])
    h = formal_hedge_diagnostic(g, ["X"], ["Y"])
    assert h.formal_hedge_certified is True
    assert h.hedge_F == "{X,Y}"
    assert h.hedge_F_prime == "{Y}"

    result = identify_effect(g, "X", "Y")
    assert result.identifiable is False
    assert result.hedge_status == "formal_hedge_certified_recursive_fail_branch"
    assert result.formal_hedge_certified == 1
    assert result.failure_reason == "FORMAL_HEDGE_CERTIFICATE_LOCAL_DISTRICT_FAIL_BRANCH_STEP28"


def test_no_formal_hedge_for_observed_dag():
    g = admg_from_edges(["X", "Y"], [("X", "Y")], [])
    result = identify_effect(g, "X", "Y")
    assert result.identifiable is True
    assert result.formal_hedge_status == "not_run_requires_recursive_id_fail_branch"
    assert result.formal_hedge_certified == 0


def test_no_formal_hedge_for_identifiable_frontdoor_graph():
    # Classic front-door shape: X -> Z -> Y with X <-> Y.  The older hedge
    # diagnostic over-certified this because F roots {X,Y} and F' roots {Y}
    # were treated as sufficient when F' roots were outcome ancestors.  A
    # formal hedge requires the same roots, so this must remain identifiable.
    g = admg_from_edges(["X", "Z", "Y"], [("X", "Z"), ("Z", "Y")], [("X", "Y")])
    h = formal_hedge_diagnostic(g, ["X"], ["Y"])
    assert h.formal_hedge_certified is False
    assert h.formal_hedge_status == "not_certified"

    result = identify_effect(g, "X", "Y", mediators=["Z"])
    assert result.identifiable is True
    assert result.id_strategy == "frontdoor_limited"
    assert result.formal_hedge_certified == 0
    assert result.id_contract_status == "identified_with_formula_and_proof_trace"


def test_no_formal_hedge_for_identifiable_recursive_parent_covariate_graph():
    # X <-> Z, X -> Y, Z -> Y is identifiable by recursive district
    # decomposition.  It is not a formal hedge because F and F' do not share
    # the same roots.
    g = admg_from_edges(["X", "Z", "Y"], [("X", "Y"), ("Z", "Y")], [("X", "Z")])
    h = formal_hedge_diagnostic(g, ["X"], ["Y"])
    assert h.formal_hedge_certified is False
    assert h.formal_hedge_status == "not_certified"

    result = identify_effect(g, "X", "Y")
    assert result.identifiable is True
    assert result.id_strategy == "full_recursive_id_step2"
    assert result.formal_hedge_certified == 0
    assert result.id_contract_status == "identified_with_formula_and_proof_trace"
