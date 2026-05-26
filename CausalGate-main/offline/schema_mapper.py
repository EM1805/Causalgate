from __future__ import annotations

from runtime_env import configure_scientific_runtime
configure_scientific_runtime()


from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json


try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None


DEFAULT_SCHEMA_PATH = "schema_mapping.yaml"


def _norm(value: object) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


@dataclass
class CanonicalVariable:
    canonical_name: str
    raw_aliases: List[str]
    var_type: str = "generic"


class SchemaMapper:
    def __init__(self, spec: Dict):
        self.spec = spec or {}
        self.variables: Dict[str, CanonicalVariable] = {}
        self.alias_to_canonical: Dict[str, str] = {}
        self._build()

    def _build(self) -> None:
        raw_vars = self.spec.get("canonical_variables", {}) or {}
        for canonical_name, raw in raw_vars.items():
            aliases = list(raw.get("raw_aliases", []) or [])
            var_type = str(raw.get("type", "generic") or "generic")
            entry = CanonicalVariable(canonical_name=str(canonical_name), raw_aliases=aliases, var_type=var_type)
            self.variables[str(canonical_name)] = entry
            self.alias_to_canonical[_norm(canonical_name)] = str(canonical_name)
            for alias in aliases:
                alias = str(alias).strip()
                if alias:
                    self.alias_to_canonical[_norm(alias)] = str(canonical_name)

    @classmethod
    def load(cls, path: str | Path = DEFAULT_SCHEMA_PATH) -> "SchemaMapper":
        path = Path(path)
        if not path.exists():
            return cls({})
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() in {".yaml", ".yml"}:
            if yaml is None:
                raise RuntimeError("PyYAML is required to load YAML schema mappings.")
            spec = yaml.safe_load(text) or {}
        else:
            spec = json.loads(text)
        return cls(spec)

    def resolve(self, raw_name: str) -> Optional[str]:
        key = _norm(raw_name)
        return self.alias_to_canonical.get(key)

    def variable_type(self, canonical_name: str) -> Optional[str]:
        item = self.variables.get(canonical_name)
        return item.var_type if item else None

    def canonicalize_columns(self, columns: List[str]) -> Tuple[List[str], Dict[str, str], Dict[str, str]]:
        canonical_columns: List[str] = []
        raw_to_canonical: Dict[str, str] = {}
        canonical_to_raw: Dict[str, str] = {}
        used: Dict[str, int] = {}
        for raw_name in columns:
            canonical = self.resolve(raw_name) or str(raw_name)
            unique_name = canonical
            if unique_name in used:
                used[unique_name] += 1
                unique_name = f"{canonical}__dup{used[canonical]}"
            else:
                used[unique_name] = 0
            canonical_columns.append(unique_name)
            raw_to_canonical[str(raw_name)] = unique_name
            canonical_to_raw.setdefault(unique_name, str(raw_name))
        return canonical_columns, raw_to_canonical, canonical_to_raw

    def canonicalize_dataframe(self, df: Any) -> Tuple[Any, Dict[str, str], Dict[str, str]]:
        new_cols, raw_to_canonical, canonical_to_raw = self.canonicalize_columns(list(df.columns))
        out = df.copy()
        out.columns = new_cols
        return out, raw_to_canonical, canonical_to_raw


def load_schema_mapper(path: str | Path = DEFAULT_SCHEMA_PATH) -> SchemaMapper:
    return SchemaMapper.load(path)
