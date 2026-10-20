# CausalGate 0.6.2b1 — developer pilot

A single-tenant beta for a small group of developer evaluators, distributed as
a Python package or private authenticated API. Positioning:

> Evaluate policy conditions and supplied causal evidence before an AI agent acts.

## Changes

- Bearer authentication; decisions disabled without a configured key.
- Server-owned policy/audit configuration; remote demo writing removed.
- Body-size, JSON complexity, receive-time and process-local request limits.
- Explicit action facts and inline evidence; no filesystem evidence arguments.
- Evidence checks cannot be disabled for mutations or causal questions.
- Generic HTTP failures; no server exception paths returned to clients.
- Runtime/package version aligned; demo assets included in wheels.
- Unprivileged Docker runtime and private-pilot configuration documentation.

## Validation and rollout

The pull request records the tests actually run. Before enabling a pilot host,
configure its secret, HTTPS, upstream connection limits and log rotation.
Verify missing/wrong credentials fail, a read-only case passes, a destructive
case blocks, and a timeout never triggers downstream execution. Test with the
integration's representative actions and failure cases before connecting tools.

The API consumes integrator-supplied facts; it does not prove causality or agent
safety. No new real-world efficacy benchmark or independent security audit is
claimed. Billing, multi-tenant accounts and distributed quotas remain outside
this beta. Existing commercial/source-available license templates are unchanged.

## Rollback and compatibility

Stop the beta service and disable the integration's execution path. Returning
to the old unauthenticated API is not a safe public-host rollback. Preserve
audit logs and configuration; service unavailability is never permission to
execute. Clients must migrate policy/output paths and `enable_tool_guard` to
server configuration. Use the local CLI for demo reports.
