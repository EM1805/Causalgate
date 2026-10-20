"""Run with a freshly installed wheel, outside the source checkout."""
import json
import os
from importlib.metadata import version
from pathlib import Path
import tempfile

from fastapi.testclient import TestClient
import causalgate
from causalgate.api.security import APISettings
from causalgate.api.server import create_app
from causalgate.demo import run_product_demo
from causalgate.gate import DecisionGate


def main():
    assert causalgate.__version__ == version("causalgate")
    # Avoid an editable/source install masquerading as a wheel smoke test.
    assert "site-packages" in str(Path(causalgate.__file__).resolve())
    with tempfile.TemporaryDirectory() as work:
        os.chdir(work)
        gate = DecisionGate()
        assert Path(gate.registry_path).is_file()
        assert Path(gate.path_library_path).is_file()
        result = run_product_demo(out_dir=str(Path(work) / "showcase"))
        assert [c.decision for c in result.cases] == ["PASS", "HARD_BLOCK", "REVIEW"]
        assert all(c.matched_expected for c in result.cases)
        key = "smoke-test-only-not-a-real-key-0123456789"
        client = TestClient(create_app(APISettings(api_key=key)))
        action = {"action": "summarize_dashboard", "environment": "staging", "risk_level": "low", "action_type": "read"}
        assert client.post("/v1/guard", json=action).status_code == 401
        response = client.post("/v1/guard", json=action, headers={"Authorization": "Bearer " + key})
        assert response.status_code == 200 and response.json()["firewall_decision"] == "PASS"
        assert response.json()["executed"] is False
        print(json.dumps({"version": causalgate.__version__, "wheel_smoke": "passed", "demo_decisions": [c.decision for c in result.cases]}))


if __name__ == "__main__":
    main()
