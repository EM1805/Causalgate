from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, Iterable, Mapping, Optional


ToolExecutor = Callable[[Dict[str, Any]], Any]


def _listish(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    try:
        return [str(item) for item in value if str(item).strip()]
    except TypeError:
        return []


@dataclass
class ToolSpec:
    """Executable tool metadata used by CausalGateAgent.

    The tool registry is deliberately an allowlist: a proposed action may
    execute only when it appears here, its input schema validates, RegistryPolicy
    accepts the current agent mode, and ToolGuard separately permits execution.
    """

    name: str
    executor: Optional[ToolExecutor] = None
    action_type: str = "tool_call"
    target_resource: str = "tool"
    risk_level: str = "unknown"
    requires_approval: bool = False
    allowed_in_production: bool = False
    description: str = ""

    # Step 11 hardening metadata.
    allowed_agent_modes: list[str] = field(default_factory=list)
    side_effect_level: str = "unknown"
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    timeout_seconds: Optional[int] = None
    sandbox_required: bool = False
    requires_network: bool = False
    requires_filesystem: bool = False
    requires_credentials: bool = False

    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.allowed_agent_modes = _listish(self.allowed_agent_modes)

    def execute(self, args: Mapping[str, Any] | None = None) -> Any:
        if self.executor is None:
            raise RuntimeError(f"Tool '{self.name}' has no executor.")
        return self.executor(dict(args or {}))

    def validate_args(self, args: Mapping[str, Any] | None = None) -> list[str]:
        """Very small schema validator for runtime fail-closed checks.

        Supported schema shapes:
        - {"required": ["path", "content"]}
        - {"path": "string", "amount": "number"}
        - {"path": {"type": "string", "required": true}}
        This is not a replacement for JSON Schema; it is a dependency-light
        guardrail before ToolGuard/executor invocation.
        """

        schema = dict(self.input_schema or {})
        values = dict(args or {})
        errors: list[str] = []

        required = schema.get("required", [])
        for key in _listish(required):
            if key not in values or values.get(key) in {None, ""}:
                errors.append(f"missing required tool arg: {key}")

        type_map = {
            "string": str,
            "str": str,
            "number": (int, float),
            "float": (int, float),
            "int": int,
            "integer": int,
            "bool": bool,
            "boolean": bool,
            "object": dict,
            "dict": dict,
            "array": list,
            "list": list,
        }
        for key, spec in schema.items():
            if key == "required":
                continue
            expected = None
            required_flag = False
            if isinstance(spec, str):
                expected = spec
            elif isinstance(spec, Mapping):
                expected = spec.get("type")
                required_flag = bool(spec.get("required"))
            if required_flag and (key not in values or values.get(key) in {None, ""}):
                errors.append(f"missing required tool arg: {key}")
                continue
            if expected and key in values and values.get(key) is not None:
                py_type = type_map.get(str(expected).lower())
                if py_type is not None and not isinstance(values.get(key), py_type):
                    errors.append(f"tool arg '{key}' expected {expected}, got {type(values.get(key)).__name__}")
        return errors

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        # Callables are not JSON-serializable and should not leak in API output.
        data["executor"] = bool(self.executor)
        return data


class ToolRegistry:
    """Small stdlib-only allowlist for agent tools."""

    def __init__(self, tools: Iterable[ToolSpec] | None = None) -> None:
        self._tools: Dict[str, ToolSpec] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: ToolSpec | Mapping[str, Any], executor: ToolExecutor | None = None) -> ToolSpec:
        if isinstance(tool, Mapping):
            data = dict(tool)
            if executor is not None:
                data["executor"] = executor
            spec = ToolSpec(**data)
        else:
            spec = tool
            if executor is not None:
                spec.executor = executor

        name = str(spec.name or "").strip()
        if not name:
            raise ValueError("ToolSpec.name is required.")
        self._tools[name] = spec
        return spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(str(name or "").strip())

    def require(self, name: str) -> ToolSpec:
        spec = self.get(name)
        if spec is None:
            raise KeyError(f"Tool '{name}' is not registered in the CausalGate ToolRegistry.")
        return spec

    def names(self) -> list[str]:
        return sorted(self._tools)

    def to_dict(self) -> Dict[str, Any]:
        return {name: spec.to_dict() for name, spec in sorted(self._tools.items())}


def build_default_tool_registry() -> ToolRegistry:
    """Return an empty-by-default safe registry.

    Production users should explicitly register real executors. Keeping this
    empty prevents accidental execution during demos/tests. For a bounded demo
    registry, use ``build_sandbox_tool_registry`` from ``causalgate.agent``.
    """

    return ToolRegistry()


def build_sandbox_tool_registry(*, root_dir: str = ".", out_dir: str = "out", include_legacy_aliases: bool = True) -> ToolRegistry:
    """Lazy wrapper for the sandbox demo registry.

    Kept here for discoverability while avoiding an import cycle at module load.
    """

    from .tool_executors import build_sandbox_tool_registry as _build

    return _build(root_dir=root_dir, out_dir=out_dir, include_legacy_aliases=include_legacy_aliases)


__all__ = [
    "ToolExecutor",
    "ToolRegistry",
    "ToolSpec",
    "build_default_tool_registry",
    "build_sandbox_tool_registry",
]
