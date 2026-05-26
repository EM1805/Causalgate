# Step 5 changelog — Product API server

Step 5 turns CausalGate from a local CLI/API package into an embeddable product service.

## Added

- `causalgate.api.server`
- FastAPI app factory: `create_app()`
- Exported app: `causalgate.api.server:app`
- `GET /v1/health`
- `POST /v1/guard`
- `POST /v1/guard/markdown`
- `POST /v1/demo`
- CLI server command:

```bash
causalgate api --host 0.0.0.0 --port 8000
```

- API documentation in `docs/API_SERVER.md`
- Product API tests in `tests/test_product_api_server_step5.py`

## Product impact

CausalGate can now be integrated by:

- AI-agent runtimes
- internal workflow systems
- dashboards
- enterprise review queues
- hosted SaaS prototypes
- self-hosted deployments

The server deliberately acts as a pre-execution decision service. It returns a decision and audit package, but does not execute external tools.
