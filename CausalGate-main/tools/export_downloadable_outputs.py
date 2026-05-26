#!/usr/bin/env python3
"""Generate downloadable CausalGate product artifacts.

The bundle is intentionally small and product-oriented: it demonstrates the
agent firewall decision surface rather than internal research loops.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "out" / "downloads"
BUNDLE_DIR = OUT_DIR / "causalgate_product_outputs"
ZIP_PATH = OUT_DIR / "causalgate_product_outputs.zip"


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_import_outputs() -> Dict[str, Any]:
    from causalgate import AgentCausalFirewall, __version__

    action = {
        "request_id": "downloadable-demo-001",
        "action_name": "deploy_config_change",
        "tool_name": "deploy_config_change",
        "action_type": "mutation",
        "target_resource": "payments-service",
        "trusted_runtime_context": {
            "environment": "production",
            "risk_level": "high",
            "approval_present": False,
            "rollback_available": False,
        },
        "untrusted_llm_context": {
            "agent_rationale": "The agent believes the change will reduce latency."
        },
    }
    firewall = AgentCausalFirewall(enable_tool_guard=True)
    result = firewall.evaluate_tool_call(action).to_dict()

    metadata: Dict[str, Any] = {
        "name": "CausalGate",
        "product": "causal firewall for AI agents",
        "version": __version__,
        "primary_api": "from causalgate import AgentCausalFirewall",
        "primary_cli": "causalgate guard",
    }
    try:
        from causalgate.mcp.schemas import app_metadata, list_tool_schemas

        metadata["mcp"] = app_metadata()
        tool_schemas = {"tools": list_tool_schemas()}
    except Exception as exc:  # pragma: no cover - optional server surface
        tool_schemas = {"tools": [], "warning": {"type": type(exc).__name__, "message": str(exc)}}

    return {
        "version": __version__,
        "metadata": metadata,
        "tool_schemas": tool_schemas,
        "agent_firewall_demo": result,
        "public_api_example": {
            "python": "from causalgate import AgentCausalFirewall\nfirewall = AgentCausalFirewall()\nresult = firewall.evaluate(action='deploy_config_change', environment='production', risk_level='high')",
            "cli": "causalgate guard --action deploy_config_change --environment production --risk-level high",
        },
    }


def _build_markdown_report(outputs: Dict[str, Any]) -> str:
    result = outputs.get("agent_firewall_demo", {})
    return f"""# CausalGate product outputs

Generated at: `{_now()}`

Version: `{outputs.get('version', 'unknown')}`

## What this bundle contains

- `metadata.json`: product metadata snapshot.
- `agent_firewall_demo.json`: example agent-action firewall decision.
- `public_api_example.json`: Python and CLI entry points.
- `tool_schemas.json`: optional MCP/server tool schema snapshot when available.
- `manifest.json`: file manifest and generation metadata.

## Demo decision

| Field | Value |
|---|---|
| Firewall decision | `{result.get('firewall_decision', 'unknown')}` |
| Execution action | `{result.get('execution_action', 'unknown')}` |
| Blocked | `{result.get('blocked', 'unknown')}` |
| Needs approval | `{result.get('needs_approval', 'unknown')}` |
| Tool | `{result.get('tool_name', 'unknown')}` |

## Safety note

These outputs are demonstration artifacts. They show how CausalGate evaluates a
proposed agent action before execution; they are not proof of causality and not a
substitute for human review in high-impact settings.
"""


def _zip_dir(source_dir: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as zf:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(source_dir.parent))


def main() -> int:
    os.chdir(ROOT)
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)

    outputs = _safe_import_outputs()
    files = {
        "metadata.json": outputs["metadata"],
        "tool_schemas.json": outputs["tool_schemas"],
        "agent_firewall_demo.json": outputs["agent_firewall_demo"],
        "public_api_example.json": outputs["public_api_example"],
    }

    for name, payload in files.items():
        _write_json(BUNDLE_DIR / name, payload)

    report = _build_markdown_report(outputs)
    _write_text(BUNDLE_DIR / "README_OUTPUTS.md", report)

    manifest = {
        "generated_at": _now(),
        "version": outputs.get("version"),
        "bundle_dir": str(BUNDLE_DIR.relative_to(ROOT)),
        "zip_path": str(ZIP_PATH.relative_to(ROOT)),
        "files": sorted([*files.keys(), "README_OUTPUTS.md", "manifest.json"]),
        "purpose": "Downloadable CausalGate product demo artifacts for GitHub Actions and demos.",
    }
    _write_json(BUNDLE_DIR / "manifest.json", manifest)
    _zip_dir(BUNDLE_DIR, ZIP_PATH)

    print(json.dumps({"status": "ok", "bundle_dir": str(BUNDLE_DIR), "zip_path": str(ZIP_PATH)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
