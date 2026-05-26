from __future__ import annotations

import html
import json
from dataclasses import is_dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Mapping


def _to_dict(result: Any) -> Dict[str, Any]:
    if hasattr(result, "to_dict"):
        return dict(result.to_dict())
    if is_dataclass(result):
        return asdict(result)
    return dict(result) if isinstance(result, Mapping) else {"result": result}


def render_markdown_report(result: Any) -> str:
    payload = _to_dict(result)
    authority = dict(payload.get("authority_evaluation") or {})
    policy = dict(payload.get("policy_evaluation") or {})
    reasons = payload.get("reason_codes") or []
    lines = [
        "# CausalGate Agent Action Report",
        "",
        f"**Decision:** `{payload.get('firewall_decision', 'UNKNOWN')}`",
        f"**Execution action:** `{payload.get('execution_action', 'UNKNOWN')}`",
        f"**Tool/action:** `{payload.get('tool_name', '')}`",
        f"**Request ID:** `{payload.get('request_id', '')}`",
        f"**Decision digest:** `{payload.get('decision_digest', '')}`",
        "",
        "## Summary",
        "",
        str(payload.get("summary") or "No summary supplied."),
        "",
    ]
    if authority:
        lines.extend([
            "## Causal authority",
            "",
            f"**Score:** `{authority.get('authority_score', 'n/a')}/100`",
            f"**Level:** `{authority.get('authority_level', 'n/a')}`",
            f"**Authority decision:** `{authority.get('authority_decision', 'n/a')}`",
            f"**Threshold profile:** `{authority.get('threshold_profile', 'n/a')}`",
            "",
            "### Reasons",
            "",
        ])
        for item in authority.get("reasons") or []:
            lines.append(f"- {item}")
        lines.extend(["", "### Required next steps", ""])
        next_steps = authority.get("required_next_steps") or []
        if next_steps:
            for item in next_steps:
                lines.append(f"- {item}")
        else:
            lines.append("- None recorded.")
        lines.append("")
    else:
        lines.extend([
            "## Causal authority",
            "",
            "No causal evidence package was supplied for this action.",
            "",
        ])

    lines.extend([
        "## Policy evaluation",
        "",
        f"**Policy decision:** `{policy.get('firewall_decision', 'UNKNOWN')}`",
        f"**Matched rules:** `{', '.join(policy.get('matched_rule_ids') or [])}`",
        "",
        "## Reason codes",
        "",
    ])
    if reasons:
        for code in reasons:
            lines.append(f"- `{code}`")
    else:
        lines.append("- None")
    lines.extend(["", "## Machine-readable payload", "", "```json", json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), "```", ""])
    return "\n".join(lines)



def render_html_report(result: Any) -> str:
    """Render a compact standalone HTML audit report for demos and buyers."""
    payload = _to_dict(result)
    authority = dict(payload.get("authority_evaluation") or {})
    policy = dict(payload.get("policy_evaluation") or {})
    reasons = payload.get("reason_codes") or []

    def esc(value: Any) -> str:
        return html.escape(str(value if value is not None else ""))

    decision = esc(payload.get("firewall_decision", "UNKNOWN"))
    score = authority.get("authority_score", "n/a") if authority else "n/a"
    level = authority.get("authority_level", "n/a") if authority else "n/a"
    required = authority.get("required_next_steps") if authority else []
    auth_reasons = authority.get("reasons") if authority else []

    reason_items = "\n".join(f"<li>{esc(item)}</li>" for item in auth_reasons) or "<li>No causal evidence package supplied.</li>"
    required_items = "\n".join(f"<li>{esc(item)}</li>" for item in required) or "<li>None recorded.</li>"
    code_items = "\n".join(f"<li><code>{esc(code)}</code></li>" for code in reasons) or "<li>None</li>"
    raw_json = esc(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))

    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>CausalGate Agent Action Report</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif; margin: 0; background: #0f172a; color: #e5e7eb; }}
    main {{ max-width: 960px; margin: 0 auto; padding: 40px 20px; }}
    .card {{ background: #111827; border: 1px solid #253047; border-radius: 18px; padding: 24px; margin: 18px 0; box-shadow: 0 18px 60px rgba(0,0,0,.24); }}
    .decision {{ display: inline-block; padding: 8px 12px; border-radius: 999px; background: #1f2937; font-weight: 700; letter-spacing: .04em; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }}
    .metric {{ background: #0b1220; border: 1px solid #263348; border-radius: 14px; padding: 16px; }}
    .metric b {{ display:block; color:#94a3b8; font-size:12px; text-transform:uppercase; margin-bottom:6px; }}
    pre {{ overflow:auto; background:#020617; border-radius:14px; padding:16px; border:1px solid #1f2937; }}
    code {{ color:#dbeafe; }}
    h1, h2 {{ margin-bottom: 10px; }}
    li {{ margin: 6px 0; }}
  </style>
</head>
<body>
<main>
  <h1>CausalGate Agent Action Report</h1>
  <p class=\"decision\">Decision: {decision}</p>
  <div class=\"card grid\">
    <div class=\"metric\"><b>Authority score</b>{esc(score)}/100</div>
    <div class=\"metric\"><b>Authority level</b>{esc(level)}</div>
    <div class=\"metric\"><b>Execution action</b>{esc(payload.get('execution_action', 'UNKNOWN'))}</div>
    <div class=\"metric\"><b>Request ID</b>{esc(payload.get('request_id', ''))}</div>
  </div>
  <section class=\"card\">
    <h2>Summary</h2>
    <p>{esc(payload.get('summary') or 'No summary supplied.')}</p>
  </section>
  <section class=\"card\">
    <h2>Causal authority reasons</h2>
    <ul>{reason_items}</ul>
    <h3>Required next steps</h3>
    <ul>{required_items}</ul>
  </section>
  <section class=\"card\">
    <h2>Policy evaluation</h2>
    <p><b>Policy decision:</b> <code>{esc(policy.get('firewall_decision', 'UNKNOWN'))}</code></p>
    <p><b>Matched rules:</b> <code>{esc(', '.join(policy.get('matched_rule_ids') or []))}</code></p>
  </section>
  <section class=\"card\">
    <h2>Reason codes</h2>
    <ul>{code_items}</ul>
  </section>
  <section class=\"card\">
    <h2>Machine-readable payload</h2>
    <pre>{raw_json}</pre>
  </section>
</main>
</body>
</html>"""


def write_html_report(result: Any, path: str | Path) -> str:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(render_html_report(result), encoding="utf-8")
    return str(path)


def write_json_report(result: Any, path: str | Path) -> str:
    payload = _to_dict(result)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return str(path)


def write_markdown_report(result: Any, path: str | Path) -> str:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(render_markdown_report(result), encoding="utf-8")
    return str(path)


__all__ = ["render_markdown_report", "render_html_report", "write_json_report", "write_markdown_report", "write_html_report"]
