from __future__ import annotations

import json
from pathlib import Path


REQUIRED_KEYS = {
    "nodes",
    "edges",
    "queries",
    "assumptions",
    "structural_equations",
    "exogenous",
    "data_path",
    "safety_policy",
}


def test_scm_input_templates_are_valid_json_and_have_required_blocks():
    root = Path(__file__).resolve().parents[1]
    template_dir = root / "examples" / "scm_templates"
    templates = sorted(template_dir.glob("scm_input.template.*.json"))
    assert templates, "expected SCM input templates"
    for path in templates:
        payload = json.loads(path.read_text(encoding="utf-8"))
        missing = REQUIRED_KEYS - set(payload)
        assert not missing, f"{path.name} missing {sorted(missing)}"
        assert payload["nodes"], f"{path.name} should define nodes"
        assert payload["edges"], f"{path.name} should define edges"
        assert payload["queries"], f"{path.name} should define at least one causal query"
        assert payload["safety_policy"].get("require_identification") is True
