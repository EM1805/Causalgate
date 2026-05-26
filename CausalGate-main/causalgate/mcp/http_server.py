from __future__ import annotations

"""HTTP MCP bridge for CausalGate."""

import os
from typing import Any, Dict, List, Mapping

from causalgate import __version__

from .schemas import app_metadata
from .server import handle_message
from .tools import call_tool, list_tools

SERVICE_NAME = "causalgate-mcp-http"
DEFAULT_AUTO_GOAL = "Genera e migliora una ipotesi scientifica"
COMPLETE_DEMO_MODE = "complete_causal_json"
NATIVE_DEMO_MODE = "native_json_only"


def _external_base_url() -> str:
    return os.getenv("CAUSALGATE_PUBLIC_BASE_URL", "").strip().rstrip("/")


def capabilities_payload() -> Dict[str, Any]:
    return {
        "native_hypothesis_agent": True,
        "external_llm_used": False,
        "gemini_disabled": True,
        "gemini_propose_or_revise": False,
        "gemini_language_only": False,
        "gemini_configured": False,
        "output_format": "json_only",
        "max_steps_default": int(os.getenv("CAUSALGATE_DEMO_MAX_STEPS", "6") or "6"),
        "demo_default_mode": COMPLETE_DEMO_MODE,
        "demo_available_modes": [COMPLETE_DEMO_MODE, NATIVE_DEMO_MODE],
        "demo_requires_user_text": False,
        "demo_shows_cycles": True,
        "demo_full_pipeline": True,
        "native_physics_math_full_pipeline": True,
        "demo_available_modes_description": {
            COMPLETE_DEMO_MODE: "Synthetic empirical causal demo with Veto, SCM-ID, Estimation, claim audit, and internal veto revision.",
            NATIVE_DEMO_MODE: "Native deterministic physics/math hypothesis discovery followed by the same dialogue/veto pipeline; SCM-ID and Estimation run when applicable and return not_applicable for mathematical conjectures.",
        },
        "demo_pipeline_components": [
            "Native/HTTP demo",
            "LLMDialogueOrchestrator",
            "HypothesisDiscoveryAgent",
            "HypothesisVeto",
            "SCM-ID identification",
            "Estimation adapter",
            "FalsificationPolicy",
            "ClaimLevelAudit",
        ],
        "guardrails": [
            "FINAL_CANDIDATE means candidate for testing or formal review, not confirmed law/proof.",
            "The complete demo includes a synthetic causal hypothesis so SCM-ID and Estimation can run safely.",
            "Native physics/math generation creates a structured candidate only; CausalGate veto still controls claim level.",
            "Mathematical conjectures pass through the pipeline with empirical SCM-ID/Estimation marked not_applicable.",
            "The demo endpoint returns JSON only and does not add natural-language rendering.",
        ],
    }


def health_payload() -> Dict[str, Any]:
    tools = list_tools().get("tools", [])
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": __version__,
        "mcp_endpoint": "/mcp",
        "metadata_endpoint": "/metadata",
        "tools_endpoint": "/tools",
        "capabilities_endpoint": "/capabilities",
        "demo_endpoint": "/demo",
        "tool_count": len(tools),
        "tools": [tool.get("name") for tool in tools if isinstance(tool, Mapping)],
        "capabilities": capabilities_payload(),
    }


def metadata_payload() -> Dict[str, Any]:
    meta = app_metadata(_external_base_url() or None)
    meta["capabilities"] = capabilities_payload()
    return meta


def _jsonrpc_error(msg_id: Any, code: int, message: str, data: Any = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}
    if data is not None:
        payload["error"]["data"] = data
    return payload


def _complete_demo_hypothesis() -> Dict[str, Any]:
    """Synthetic auditable causal hypothesis for the full HF demo path.

    The numbers are demo inputs, not real-world evidence. They exist so the
    public demo can exercise Discovery/orchestration, veto, SCM-ID and Estimation
    in one JSON-only run without needing uploaded data or private files.
    """

    return {
        "hypothesis_id": "HF_complete_demo_backdoor_001",
        "claim": "In a synthetic demo study, increasing X may increase Y after adjusting for pre-treatment confounder Z.",
        "claim_level": "causally_identified",
        "domain": "empirical_causal_demo",
        "treatment": "X",
        "outcome": "Y",
        "confounders": ["Z"],
        "adjustment_set": ["Z"],
        "dag": {
            "nodes": ["X", "Y", "Z", "N"],
            "edges": [["Z", "X"], ["Z", "Y"], ["X", "Y"]],
        },
        "assumptions": [
            "Z is measured before X and Y.",
            "The supplied DAG is the demo causal graph.",
            "No unmeasured confounding remains after adjusting for Z in this synthetic example.",
        ],
        "identification_strategy": "validated backdoor adjustment using Z",
        "falsification_tests": [
            "Future-X placebo test should not predict present Y.",
            "Negative control outcome N should not change under X after adjustment.",
        ],
        "measurable_predictions": [
            "Estimated Y should increase when X increases under adjustment for Z.",
            "The sign of the effect should remain positive in bootstrap resamples.",
        ],
        "negative_controls": ["N"],
        "negative_control_variables": ["N"],
        "negative_control_tests": ["N should not increase under X after adjustment for Z."],
        "placebo_tests": ["Future-X placebo must fail."],
        "sensitivity_checks": ["Hidden-confounding sensitivity check and CI review."],
        "data_requirements": ["Synthetic demo payload includes an external effect estimate and confidence interval."],
        "test_plan": "Run SCM-ID, load the supplied demo estimate, keep claim bounded as candidate-level evidence.",
        "metadata": {
            "demo_pipeline": "complete_causal_json",
            "synthetic_demo": True,
            "effect_estimate": 0.12,
            "ci_low": 0.04,
            "ci_high": 0.20,
            "support_n": 240,
            "treated_n": 120,
            "control_n": 120,
            "robustness_status": "demo_supplied_not_independently_replicated",
            "negative_control_status": "not_run_demo_payload",
            "placebo_status": "not_run_demo_payload",
            "sensitivity_status": "not_run_demo_payload",
            "estimator": "demo_external_effect_estimate",
        },
    }


def _demo_tool_name(payload: Mapping[str, Any]) -> str:
    mode = str(payload.get("mode") or payload.get("demo_mode") or COMPLETE_DEMO_MODE).strip().lower()
    if mode in {NATIVE_DEMO_MODE, "native", "generate", "generative"}:
        return "causalgate_run_native_json_hypothesis"
    return "causalgate_run_llm_dialogue"


def _demo_arguments(payload: Mapping[str, Any]) -> Dict[str, Any]:
    goal = str(payload.get("goal") or DEFAULT_AUTO_GOAL).strip() or DEFAULT_AUTO_GOAL
    mode = str(payload.get("mode") or payload.get("demo_mode") or COMPLETE_DEMO_MODE).strip().lower() or COMPLETE_DEMO_MODE
    max_steps = payload.get("max_steps") or payload.get("max_iterations") or os.getenv("CAUSALGATE_DEMO_MAX_STEPS", "6")
    try:
        max_steps_int = max(1, min(25, int(max_steps)))
    except Exception:
        max_steps_int = 6

    common = {
        "goal": goal,
        "max_steps": max_steps_int,
        "max_iterations": max_steps_int,
        "auto_expand": True,
        "agent_repair": True,
        "gemini_language_only": False,
        "output_format": "json_only",
        "demo_mode": mode,
        "write_ledger": False,
    }
    if mode in {NATIVE_DEMO_MODE, "native", "generate", "generative"}:
        return {
            **common,
            "enable_identification": bool(payload.get("enable_identification", True)),
            "native_hypothesis_agent": True,
            "full_pipeline": True,
            "pipeline_note": "Physics/math native candidates pass through discovery, dialogue loop, veto, falsification, claim audit, and SCM-ID/Estimation when applicable.",
        }
    return {
        **common,
        "goal": "Complete causal demo: Discovery/orchestration → Veto → SCM-ID → Estimation → claim audit",
        "hypothesis": _complete_demo_hypothesis(),
        "enable_identification": True,
        "auto_expand": False,
        "native_hypothesis_agent": False,
        "llm_actor": "causalgate_complete_demo_agent",
        "metadata": {"demo_pipeline": COMPLETE_DEMO_MODE, "scm_id_enabled": True, "estimation_demo_payload": True},
    }


def _demo_html() -> str:
    return """<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>CausalGate Complete JSON Demo</title>
  <style>
    :root { color-scheme: light dark; }
    body { font-family: system-ui, -apple-system, Segoe UI, sans-serif; margin: 0; padding: 20px; line-height: 1.45; }
    main { max-width: 980px; margin: 0 auto; }
    h1 { font-size: 1.6rem; margin-bottom: 0.25rem; }
    h2 { font-size: 1.15rem; margin: 0 0 10px; }
    .card { border: 1px solid #ccc; border-radius: 14px; padding: 16px; margin: 14px 0; }
    input, select { width: 100%; box-sizing: border-box; padding: 12px; border-radius: 10px; border: 1px solid #aaa; font: inherit; }
    button { width: 100%; box-sizing: border-box; padding: 16px; border: 0; border-radius: 12px; font-size: 1.05rem; font-weight: 900; cursor: pointer; background: #2563eb; color: white; }
    button:disabled { opacity: 0.6; cursor: wait; }
    pre { white-space: pre-wrap; word-break: break-word; background: rgba(127,127,127,0.12); border-radius: 12px; padding: 14px; overflow-x: auto; }
    code { background: rgba(127,127,127,0.16); padding: 1px 4px; border-radius: 5px; }
    .muted { opacity: 0.75; }
    .ok { color: #15803d; font-weight: 800; }
    .warn { color: #b45309; font-weight: 800; }
    .grid { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); }
    .summary-grid { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); margin: 10px 0; }
    .kv { border: 1px solid rgba(127,127,127,0.35); border-radius: 10px; padding: 10px; }
    .kv b { display: block; font-size: 0.78rem; opacity: 0.7; text-transform: uppercase; letter-spacing: 0.04em; }
    .cycle { border-left: 4px solid #2563eb; padding: 10px 0 10px 12px; margin: 12px 0; background: rgba(37,99,235,0.06); border-radius: 0 10px 10px 0; }
    .cycle-title { font-weight: 900; margin-bottom: 6px; }
    .pill { display: inline-block; padding: 4px 8px; margin: 3px 4px 3px 0; border-radius: 999px; background: rgba(37,99,235,0.14); font-weight: 750; }
    .small { font-size: 0.92rem; }
  </style>
</head>
<body>
  <main>
    <h1>🧪 CausalGate Complete JSON Demo</h1>
    <p class="muted">Premi Run: la modalità completa esegue Veto, SCM-ID ed Estimation su una hypothesis causale sintetica. La modalità generativa fisica/matematica passa anch’essa dal loop scientifico completo, con SCM-ID/Estimation quando applicabili.</p>

    <section class="card">
      <div class="grid">
        <div><label for="maxSteps"><b>Max steps</b></label><input id="maxSteps" type="number" min="1" max="25" value="6" /></div>
        <div><label for="mode"><b>Mode</b></label><select id="mode"><option value="complete_causal_json">Complete: SCM-ID + Estimation</option><option value="native_json_only">Generative: physics/math full pipeline</option></select></div>
      </div>
      <p class="muted">L’endpoint <code>/demo/run</code> restituisce il payload JSON completo, senza traduzione finale in linguaggio naturale.</p>
      <button id="run">Run demo</button>
    </section>

    <section class="card"><div id="status" class="muted">Ready.</div></section>
    <section class="card"><h2>Cicli CausalGate</h2><div id="cycleOutput" class="muted">I cicli compariranno qui dopo il run.</div></section>
    <section class="card"><h2>JSON completo</h2><pre id="rawOutput">Il JSON comparirà qui.</pre></section>
  </main>

  <script>
    const runButton = document.getElementById('run');
    const rawOutput = document.getElementById('rawOutput');
    const cycleOutput = document.getElementById('cycleOutput');
    const statusBox = document.getElementById('status');
    const maxStepsBox = document.getElementById('maxSteps');
    const modeBox = document.getElementById('mode');
    function escapeHtml(value) { return String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;'); }
    function asArray(value) { if (Array.isArray(value)) return value; if (value === undefined || value === null || value === '') return []; return [value]; }
    function pillList(values) { const items = asArray(values); return items.length ? items.map(item => `<span class="pill">${escapeHtml(item)}</span>`).join(' ') : '<span class="muted">nessuno</span>'; }
    function renderCycles(data) {
      const result = data && data.result ? data.result : {};
      const turns = Array.isArray(result.turns) ? result.turns : [];
      const finalHypothesis = result.final_hypothesis || {};
      const verdict = result.final_verdict || result.initial_verdict || {};
      const identification = verdict.identification || {};
      const estimation = verdict.estimation || {};
      const summary = `
        <div class="summary-grid">
          <div class="kv"><b>Goal</b>${escapeHtml(result.goal || '')}</div>
          <div class="kv"><b>Status finale</b>${escapeHtml(result.status || '')}</div>
          <div class="kv"><b>Decisione finale</b>${escapeHtml(result.final_decision || '')}</div>
          <div class="kv"><b>Cicli completati</b>${escapeHtml(result.steps_completed ?? turns.length)}</div>
          <div class="kv"><b>SCM-ID</b>${escapeHtml(identification.identification_strategy || identification.identification_status || (identification.not_applicable ? 'not_applicable' : 'n/a'))}</div>
          <div class="kv"><b>Estimation</b>${escapeHtml(estimation.estimation_status || 'n/a')}</div>
        </div>
        <div class="small"><b>Ipotesi finale:</b> ${escapeHtml(finalHypothesis.claim || '')}</div>`;
      if (!turns.length) return summary + '<p class="muted">Nessun ciclo dettagliato restituito.</p>';
      const timeline = turns.map((turn, index) => {
        const verdict = turn.verdict || {};
        const hypothesis = turn.hypothesis || {};
        const expansion = turn.expansion || {};
        const id = verdict.identification || {};
        const est = verdict.estimation || {};
        const idStatus = id.identification_strategy || id.identification_status || (id.not_applicable ? 'not_applicable' : 'n/a');
        const next = turn.next_instruction || verdict.next_instruction || '';
        return `<div class="cycle">
          <div class="cycle-title">Ciclo ${escapeHtml(index + 1)} · Step ${escapeHtml(turn.step || '')} · ${escapeHtml(turn.actor || 'causalgate')} · ${escapeHtml(turn.status || verdict.decision || '')}</div>
          <div class="small"><b>Decisione:</b> ${escapeHtml(verdict.decision || turn.status || '')}</div>
          <div class="small"><b>Claim level:</b> ${escapeHtml(verdict.claim_level || hypothesis.claim_level || '')}</div>
          ${hypothesis.claim ? `<div class="small"><b>Claim valutato:</b> ${escapeHtml(hypothesis.claim)}</div>` : ''}
          ${verdict.reason ? `<div class="small"><b>Motivo:</b> ${escapeHtml(verdict.reason)}</div>` : ''}
          <div class="small"><b>SCM-ID:</b> ${escapeHtml(idStatus)} · identified=${escapeHtml(id.identified ?? (id.not_applicable ? 'not_applicable' : 'n/a'))}</div>
          <div class="small"><b>Estimation:</b> ${escapeHtml(est.estimation_status || 'n/a')} · effect=${escapeHtml(est.effect_estimate ?? 'n/a')}</div>
          <div class="small"><b>Missing items:</b> ${pillList(verdict.missing_items || [])}</div>
          <div class="small"><b>Required tests:</b> ${pillList(verdict.required_tests || [])}</div>
          ${expansion.state || expansion.next_required_step || expansion.applied_revision ? `<div class="small"><b>Espansione:</b> ${escapeHtml(expansion.state || expansion.next_required_step || expansion.applied_revision)}</div>` : ''}
          ${next ? `<div class="small"><b>Next instruction:</b> ${escapeHtml(next)}</div>` : ''}
        </div>`;
      }).join('');
      return summary + timeline;
    }
    runButton.addEventListener('click', async () => {
      runButton.disabled = true; statusBox.textContent = 'Running JSON demo...'; statusBox.className = 'warn'; cycleOutput.innerHTML = '<p class="muted">Sto eseguendo i cicli...</p>'; rawOutput.textContent = 'Waiting for JSON...';
      try {
        const response = await fetch('/demo/run', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ max_steps: Number(maxStepsBox.value || 6), mode: modeBox.value }) });
        const data = await response.json();
        statusBox.textContent = response.ok ? 'Done.' : 'Request returned an error.'; statusBox.className = response.ok ? 'ok' : 'warn'; cycleOutput.innerHTML = renderCycles(data); rawOutput.textContent = JSON.stringify(data, null, 2);
      } catch (err) { statusBox.textContent = 'Network or server error.'; statusBox.className = 'warn'; cycleOutput.textContent = String(err); rawOutput.textContent = String(err); }
      finally { runButton.disabled = false; }
    });
  </script>
</body>
</html>"""


def handle_mcp_http_payload(payload: Any) -> Dict[str, Any] | List[Dict[str, Any]] | None:
    if isinstance(payload, list):
        responses: List[Dict[str, Any]] = []
        for item in payload:
            if not isinstance(item, Mapping):
                responses.append(_jsonrpc_error(None, -32600, "Invalid JSON-RPC batch item"))
                continue
            response = handle_message(item)
            if response is not None:
                responses.append(response)
        return responses
    if not isinstance(payload, Mapping):
        return _jsonrpc_error(None, -32600, "Invalid JSON-RPC request object")
    return handle_message(payload)


def handle_tool_call_http_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
    name = payload.get("name")
    arguments = payload.get("arguments") if isinstance(payload.get("arguments"), Mapping) else {}
    if not isinstance(name, str) or not name.strip():
        return {"ok": False, "error": {"code": "MISSING_TOOL_NAME", "message": "POST /tools/call requires a non-empty string field: name"}}
    result = call_tool(name.strip(), arguments)
    return {"ok": "error" not in result and result.get("ok") is not False, "tool": name.strip(), "result": result}


def create_app() -> Any:
    try:
        from fastapi import FastAPI, Request
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import HTMLResponse, JSONResponse, Response
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("FastAPI HTTP server dependencies are missing. Install with: pip install fastapi uvicorn") from exc
    globals()["FastAPI"] = FastAPI; globals()["Request"] = Request; globals()["HTMLResponse"] = HTMLResponse; globals()["JSONResponse"] = JSONResponse; globals()["Response"] = Response
    app = FastAPI(title="CausalGate MCP HTTP Server", version=__version__, description="HTTP bridge exposing CausalGate scientific/causal veto tools over MCP-style JSON-RPC.")
    origins = [origin.strip() for origin in os.getenv("CAUSALGATE_CORS_ORIGINS", "*").split(",") if origin.strip()] or ["*"]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["*"])

    @app.get("/")
    async def root() -> HTMLResponse: return HTMLResponse(_demo_html())
    @app.get("/health")
    async def health() -> Dict[str, Any]: return health_payload()
    @app.get("/metadata")
    async def metadata() -> Dict[str, Any]: return metadata_payload()
    @app.get("/capabilities")
    async def capabilities() -> Dict[str, Any]: return capabilities_payload()
    @app.get("/tools")
    async def tools() -> Dict[str, Any]: return list_tools()
    @app.get("/demo")
    async def demo() -> HTMLResponse: return HTMLResponse(_demo_html())

    @app.post("/demo/run")
    async def demo_run(request: Request) -> JSONResponse:
        try: payload = await request.json()
        except Exception: payload = {}
        if not isinstance(payload, Mapping): payload = {}
        result = handle_tool_call_http_payload({"name": _demo_tool_name(payload), "arguments": _demo_arguments(payload)})
        return JSONResponse(result, status_code=200 if result.get("ok") else 400)

    @app.post("/tools/call")
    async def tools_call(request: Request) -> JSONResponse:
        try: payload = await request.json()
        except Exception: return JSONResponse({"ok": False, "error": {"code": "INVALID_JSON", "message": "Request body must be JSON."}}, status_code=400)
        if not isinstance(payload, Mapping): return JSONResponse({"ok": False, "error": {"code": "INVALID_BODY", "message": "Request body must be a JSON object."}}, status_code=400)
        result = handle_tool_call_http_payload(payload)
        return JSONResponse(result, status_code=200 if result.get("ok") else 400)

    @app.post("/mcp")
    async def mcp(request: Request) -> Response:
        try: payload = await request.json()
        except Exception: return JSONResponse(_jsonrpc_error(None, -32700, "Parse error: request body must be JSON."), status_code=400)
        response = handle_mcp_http_payload(payload)
        if response is None: return Response(status_code=204)
        return JSONResponse(response)

    @app.get("/.well-known/ai-plugin.json")
    async def ai_plugin_metadata() -> Dict[str, Any]:
        meta = metadata_payload()
        return {"schema_version": "v1", "name_for_human": meta["name"], "name_for_model": meta["slug"], "description_for_human": meta["description"], "description_for_model": meta["description"], "auth": {"type": "none"}, "api": {"type": "mcp", "url": meta["mcp_endpoint"]}}
    return app


try:
    app = create_app()
except RuntimeError:  # pragma: no cover
    app = None


if __name__ == "__main__":  # pragma: no cover
    import uvicorn
    uvicorn.run("causalgate.mcp.http_server:app", host="0.0.0.0", port=int(os.getenv("PORT", "7860")))
