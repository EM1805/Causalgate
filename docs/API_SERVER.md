# CausalGate beta API — 0.6.2b1

An authenticated, single-tenant decision service for a small developer pilot.
It evaluates supplied action facts and evidence and never executes tools.
The integrator must supply trusted facts from its backend, keeping its key out
of model context and browser code. Authentication does not prove the truth of
submitted evidence. Scores are policy heuristics, not calibrated probabilities.

## Install and run

Use Python 3.11 or 3.12 in a virtual environment. From a source checkout:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[server]'
export CAUSALGATE_API_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
causalgate api --host 127.0.0.1 --port 8000
```

On Windows PowerShell activate `.venv\Scripts\Activate.ps1`, then set the key
with `$env:CAUSALGATE_API_KEY = python -c "import secrets; print(secrets.token_urlsafe(32))"`.
Keep the generated key private. `.env.example` is a reference; the application
does not automatically load `.env`. Missing credentials disable decisions with
HTTP 503. Weak configured keys fail startup.

## Endpoints

| Method and path | Access | Purpose |
| --- | --- | --- |
| `GET /v1/health` | Public | Process liveness and service metadata |
| `GET /v1/ready` | Public | 200 when an API key is configured, otherwise 503 |
| `POST /v1/guard` | Bearer | JSON decision and audit details |
| `POST /v1/guard/markdown` | Bearer | The same decision as Markdown |

The former `POST /v1/demo` route is removed: HTTP clients cannot create files.
Generate the showcase locally with `causalgate demo --out-dir out/demo`.
`/docs` and `/openapi.json` are disabled by default; when enabled they also
require the bearer header (fetch them with an authenticated client).

```bash
curl http://127.0.0.1:8000/v1/ready
curl -X POST http://127.0.0.1:8000/v1/guard \
  -H "Authorization: Bearer $CAUSALGATE_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"action":"summarize_dashboard","environment":"staging","risk_level":"low","action_type":"read"}'
```

The read-only example returns `PASS` with `executed: false`. For a destructive
production example change the action to `delete_resource`, risk to `critical`
and action type to `delete`, leaving approval/rollback absent: expect `HARD_BLOCK`.

## Operator configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `CAUSALGATE_API_KEY` | Empty | At least 32 non-whitespace ASCII characters; generate randomly |
| `CAUSALGATE_API_POLICY_PATH` | Built-in | Operator-owned policy file |
| `CAUSALGATE_API_AUDIT_LOG` | Unset | Operator-owned JSONL log path; configure retention/rotation |
| `CAUSALGATE_API_ENABLE_TOOL_GUARD` | `0` | Optional deeper checks, operator-controlled |
| `CAUSALGATE_API_ENABLE_DOCS` | `0` | Authenticated docs/schema |
| `CAUSALGATE_API_REQUESTS_PER_MINUTE` | `60` | Global rolling window per worker, shared by all callers |
| `CAUSALGATE_API_MAX_BODY_BYTES` | `65536` | Request body limit, configurable from 1024 to 1048576 |
| `CAUSALGATE_API_BODY_TIMEOUT_SECONDS` | `10` | Complete body receive deadline, maximum 60 |

Requests cannot set policies, audit paths, output paths or ToolGuard selection.
Evidence must be an inline JSON object, never a server file path. Unknown fields
return 422. Accepted fields cover action/tool facts, split trusted/untrusted
contexts, inline evidence, bounded graphs/queries and request/message identifiers.
Every decision needs an explicit environment, risk (`low`, `medium`, `high`,
`critical`) and action type (`read`, `query`, `mutation`, `write`, `delete`,
`destructive`, `execute`, `communicate`, `share`). Boolean fields must be JSON
booleans. Mutations and causal questions always require evidence checks;
`require_causal_evidence: false` cannot disable them.

Graphs are limited to eight nodes and 32 edges; JSON depth to 24 and values to
5000. Duplicate keys and non-finite numbers are rejected. Both declared and
streamed body lengths are checked. Unexpected errors return generic failures.
Callers must not execute on a non-200 response, timeout, REVIEW or HARD_BLOCK.

## Pilot hosting

Run one worker behind HTTPS and an upstream connection/concurrency limit.
The in-memory rate window resets on restart and is not a distributed quota.
Multiple workers, per-customer accounts/quotas and unauthenticated/volumetric
abuse need an upstream API gateway. This beta is for one trusted integration,
not anonymous access or a multi-tenant SaaS. Rotate the key by replacing the
server secret and restarting; previous credentials immediately lose access.

```bash
docker build -t causalgate:0.6.2b1 .
docker run --rm -p 127.0.0.1:7860:7860 \
  -e CAUSALGATE_API_KEY \
  -v causalgate-audit:/data causalgate:0.6.2b1
```

The image uses an unprivileged user and logs to `/data/decisions.jsonl`. Do not
mount unrelated writable directories or secrets. Only the product API is served;
legacy MCP/research entry points are outside this middleware's protection.
