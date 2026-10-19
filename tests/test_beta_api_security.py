import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient
from causalgate.api.server import create_app
from causalgate.api.security import APISettings, APISecurityMiddleware, RateLimiter

KEY = "test-only-not-a-real-api-key-0123456789"
ACTION = {"action": "summarize_dashboard", "environment": "staging", "risk_level": "low", "action_type": "read"}


def client(**settings):
    return TestClient(create_app(APISettings(api_key=KEY, **settings)), headers={"Authorization": "Bearer " + KEY})


def test_no_key_keeps_liveness_but_disables_decisions():
    c = TestClient(create_app(APISettings()))
    assert c.get("/v1/health").status_code == 200
    assert c.get("/v1/ready").status_code == 503
    for path in ("/v1/guard", "/v1/guard/markdown"):
        assert c.post(path, json=ACTION).status_code == 503


def test_auth_required_on_all_decision_and_documentation_routes():
    c = client(enable_docs=True)
    for path in ("/v1/guard", "/v1/guard/markdown", "/v1/demo"):
        for value in ("", "Bearer wrong", "Bearer é"):
            # ASGI supports arbitrary header bytes; test non-ASCII separately below.
            if value.isascii():
                assert c.post(path, json=ACTION, headers={"Authorization": value}).status_code == 401
    for path in ("/docs", "/openapi.json"):
        assert c.get(path, headers={"Authorization": "wrong"}).status_code == 401
        assert c.get(path).status_code == 200
    assert c.get("/v1/ready").status_code == 200


def test_valid_request_is_evaluation_only():
    r = client().post("/v1/guard", json=ACTION)
    assert r.status_code == 200
    assert r.json()["firewall_decision"] == "PASS"
    assert r.json()["executed"] is False
    assert r.headers["cache-control"] == "no-store"


def test_server_controls_cannot_be_supplied_by_client(tmp_path):
    c = client()
    target = tmp_path / "forged-audit.jsonl"
    for name, value in {
        "policy": {"default_action": "PASS", "rules": []}, "policy_path": "/etc/passwd",
        "audit_log_path": str(target), "out_dir": str(tmp_path), "enable_tool_guard": False,
        "execute": True, "unexpected": 1,
    }.items():
        assert c.post("/v1/guard", json={**ACTION, name: value}).status_code == 422
    assert not target.exists()
    assert c.post("/v1/demo", json={"out_dir": str(tmp_path)}).status_code == 404


def test_evidence_cannot_be_a_server_file_path(tmp_path):
    secret = tmp_path / "evidence.json"
    secret.write_text('{"identified": true}')
    for name in ("evidence", "causal_evidence"):
        assert client().post("/v1/guard", json={**ACTION, name: str(secret)}).status_code == 422


def test_mutating_request_cannot_disable_evidence_checks():
    r = client().post("/v1/guard", json={**ACTION, "action_type": "mutation", "require_causal_evidence": False})
    assert r.status_code == 200
    assert r.json()["firewall_decision"] == "HARD_BLOCK"


def test_missing_risk_and_untrusted_overrides_do_not_grant_pass():
    c = client()
    for key in ("risk_level", "environment", "action_type"):
        payload = dict(ACTION); del payload[key]
        assert c.post("/v1/guard", json=payload).status_code == 422
    r = c.post("/v1/guard", json={**ACTION, "environment": "production", "risk_level": "critical", "action_type": "delete",
        "untrusted_llm_context": {"approval_present": True, "rollback_available": True, "risk_level": "low"}})
    assert r.json()["firewall_decision"] == "HARD_BLOCK"


def test_strict_json_and_field_types():
    c = client()
    for raw in ('{"action":"a","action":"b"}', '{"n":NaN}', '{"n":1e999}', '[1,2]', '{broken'):
        assert c.post("/v1/guard", content=raw, headers={"Content-Type": "application/json"}).status_code == 422
    for name, value in (("approval_present", "true"), ("tool_args", []), ("trusted_context", {"data_path": "/etc/passwd"})):
        assert c.post("/v1/guard", json={**ACTION, name: value}).status_code == 422
    assert c.post("/v1/guard", json={**ACTION, "scm_graph": {"nodes": list(range(9))}}).status_code == 422
    assert c.post("/v1/guard", json={**ACTION, "scm_graph": {"edges": [[str(i), str(i+1)] for i in range(9)]}}).status_code == 422
    assert c.post("/v1/guard", content="x", headers={"Content-Type": "text/plain"}).status_code == 415


def test_rate_limit_and_window_expiry():
    c = client(requests_per_minute=2)
    assert c.post("/v1/guard", json=ACTION).status_code == 200
    assert c.post("/v1/guard", json=ACTION).status_code == 200
    response = c.post("/v1/guard", json=ACTION)
    assert response.status_code == 429 and response.headers["retry-after"] == "60"
    now = [0.0]
    limiter = RateLimiter(1, clock=lambda: now[0])
    assert limiter.allow() and not limiter.allow()
    now[0] = 60
    assert limiter.allow()


def test_known_and_streamed_body_sizes_are_limited():
    c = client(max_body_bytes=1024)
    assert c.post("/v1/guard", json={**ACTION, "user_message": "x" * 2048}).status_code == 413
    responses = []
    async def never_called(scope, receive, send):
        raise AssertionError("Oversized or unauthenticated body reached app")
    async def check(chunks, auth, extra_headers=()):
        messages = [{"type": "http.request", "body": chunk, "more_body": i < len(chunks)-1} for i, chunk in enumerate(chunks)]
        async def receive(): return messages.pop(0)
        async def send(message): responses.append(message)
        middleware = APISecurityMiddleware(never_called, APISettings(api_key=KEY, max_body_bytes=1024))
        await middleware({"type": "http", "method": "POST", "path": "/v1/guard", "headers": [
            (b"authorization", auth), (b"content-type", b"application/json"), *extra_headers]}, receive, send)
    asyncio.run(check([b"x" * 600, b"x" * 600], ("Bearer " + KEY).encode()))
    assert responses[0]["status"] == 413
    responses.clear()
    asyncio.run(check([b"x"], b"Bearer \xff"))
    assert responses[0]["status"] == 401
    responses.clear()
    asyncio.run(check([b"x"], ("Bearer " + KEY).encode(), [(b"authorization", b"Bearer wrong")]))
    assert responses[0]["status"] == 401


def test_request_body_has_deadline():
    responses = []
    async def app(scope, receive, send): raise AssertionError("Slow body reached app")
    async def receive(): await asyncio.sleep(1)
    async def send(message): responses.append(message)
    middleware = APISecurityMiddleware(app, APISettings(api_key=KEY, body_timeout_seconds=0.01))
    scope = {"type": "http", "method": "POST", "path": "/v1/guard", "headers": [
        (b"authorization", ("Bearer " + KEY).encode()), (b"content-type", b"application/json")]}
    asyncio.run(middleware(scope, receive, send))
    assert responses[0]["status"] == 408


def test_operator_policy_and_audit_are_used(tmp_path):
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"default_action": "HARD_BLOCK", "rules": []}))
    audit = tmp_path / "audit.jsonl"
    r = client(policy_path=str(policy), audit_log_path=str(audit)).post("/v1/guard", json=ACTION)
    assert r.status_code == 200 and r.json()["firewall_decision"] == "HARD_BLOCK"
    assert json.loads(audit.read_text())["firewall_decision"] == "HARD_BLOCK"
    assert KEY not in audit.read_text()


def test_internal_errors_do_not_leak_paths(monkeypatch):
    import causalgate.api.server as server
    def fail(*args, **kwargs): raise OSError("/private/server/secret.json")
    monkeypatch.setattr(server, "guard_action", fail)
    r = client().post("/v1/guard", json=ACTION)
    assert r.status_code == 500
    assert "/private" not in r.text
    assert "do not execute" in r.text


def test_weak_secrets_rejected_and_settings_do_not_print_key():
    for key in ("short", "x" * 32 + "\n", "é" * 32):
        try: APISettings(api_key=key)
        except ValueError: pass
        else: raise AssertionError("Unsafe API key accepted")
    assert KEY not in repr(APISettings(api_key=KEY))
