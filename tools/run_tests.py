#!/usr/bin/env python3
"""Small stdlib test runner for CausalGate.

The repository's tests are plain function-style tests. This runner keeps the
package self-testable even when pytest is not installed, while still supporting
pytest markers plus the tmp_path and monkeypatch fixtures used by bundled tests.

Set CAUSALGATE_OFFLINE_CORE_TESTS=1 for restricted/offline environments where
scientific dependencies such as numpy/pandas cannot be installed. In that mode,
import failures caused only by missing optional scientific dependencies are
reported as SKIP_IMPORT_DEP and do not fail the stdlib/core smoke run. Normal CI
must leave this disabled so dependency regressions remain visible.
"""
from __future__ import annotations

import importlib.util
import inspect
import os
import pathlib
import re
import sys
import tempfile
import traceback
import types
from typing import Iterable

ROOT = pathlib.Path(__file__).resolve().parents[1]
TESTS_DIR = ROOT / "tests"
OFFLINE_CORE = os.getenv("CAUSALGATE_OFFLINE_CORE_TESTS", "0").strip().lower() in {"1", "true", "yes", "on"}
OFFLINE_SKIP_MODULES = {"numpy", "pandas", "yaml"}


class _MarkShim:
    def __getattr__(self, _name: str):
        def decorator(fn=None, *args, **kwargs):
            if fn is None:
                return lambda real_fn: real_fn
            return fn
        return decorator


class _RaisesContext:
    """Tiny subset of pytest.raises used by CausalGate's stdlib runner."""

    def __init__(self, expected_exception: type[BaseException] | tuple[type[BaseException], ...], match: str | None = None) -> None:
        self.expected_exception = expected_exception
        self.match = match
        self.value: BaseException | None = None

    def __enter__(self) -> "_RaisesContext":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None:
            raise AssertionError(f"DID NOT RAISE {self.expected_exception}")
        if not issubclass(exc_type, self.expected_exception):
            return False
        if self.match is not None and not re.search(self.match, str(exc or "")):
            raise AssertionError(f"Exception message {exc!r} does not match {self.match!r}")
        self.value = exc
        return True


def _raises(expected_exception: type[BaseException] | tuple[type[BaseException], ...], *args, match: str | None = None, **kwargs):
    """Small pytest.raises replacement.

    Supports the context-manager form used by bundled tests:

        with pytest.raises(ValueError, match="..."):
            ...

    The callable form is intentionally conservative but supported for simple
    parity with pytest: ``pytest.raises(ValueError, fn, *args, **kwargs)``.
    """
    if args and callable(args[0]):
        fn = args[0]
        fn_args = args[1:]
        with _RaisesContext(expected_exception, match=match) as ctx:
            fn(*fn_args, **kwargs)
        return ctx
    return _RaisesContext(expected_exception, match=match)


class _MonkeyPatchShim:
    """Tiny subset of pytest's monkeypatch fixture used by CausalGate tests."""

    def __init__(self) -> None:
        self._env_changes: list[tuple[str, str | None]] = []
        self._attr_changes: list[tuple[object, str, object, bool]] = []

    def setenv(self, name: str, value: object) -> None:
        key = str(name)
        self._env_changes.append((key, os.environ.get(key)))
        os.environ[key] = str(value)

    def delenv(self, name: str, raising: bool = True) -> None:
        key = str(name)
        existed = key in os.environ
        if not existed and raising:
            raise KeyError(key)
        self._env_changes.append((key, os.environ.get(key)))
        os.environ.pop(key, None)

    def setattr(self, target: object, name: str | object, value: object = None, raising: bool = True) -> None:
        if isinstance(target, str):
            module_name, attr_name = target.rsplit(".", 1)
            module = __import__(module_name, fromlist=[attr_name])
            obj = module
            attr = attr_name
            val = name
        else:
            obj = target
            attr = str(name)
            val = value
        existed = hasattr(obj, attr)
        if not existed and raising:
            raise AttributeError(attr)
        old = getattr(obj, attr, None)
        self._attr_changes.append((obj, attr, old, existed))
        setattr(obj, attr, val)

    def delattr(self, target: object, name: str | None = None, raising: bool = True) -> None:
        if isinstance(target, str):
            module_name, attr_name = target.rsplit(".", 1)
            obj = __import__(module_name, fromlist=[attr_name])
            attr = attr_name
        else:
            obj = target
            attr = str(name)
        existed = hasattr(obj, attr)
        if not existed and raising:
            raise AttributeError(attr)
        old = getattr(obj, attr, None)
        self._attr_changes.append((obj, attr, old, existed))
        if existed:
            delattr(obj, attr)

    def undo(self) -> None:
        for obj, attr, old, existed in reversed(self._attr_changes):
            if existed:
                setattr(obj, attr, old)
            elif hasattr(obj, attr):
                delattr(obj, attr)
        self._attr_changes.clear()
        for key, old in reversed(self._env_changes):
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
        self._env_changes.clear()


def _install_pytest_shim() -> None:
    if "pytest" in sys.modules:
        pytest = sys.modules["pytest"]
        if not hasattr(pytest, "mark"):
            pytest.mark = _MarkShim()
        if not hasattr(pytest, "raises"):
            pytest.raises = _raises
        return
    pytest = types.ModuleType("pytest")
    pytest.mark = _MarkShim()
    pytest.raises = _raises
    sys.modules["pytest"] = pytest


def _iter_test_files(args: list[str]) -> list[pathlib.Path]:
    if args:
        out: list[pathlib.Path] = []
        for raw in args:
            p = pathlib.Path(raw)
            if p.is_dir():
                out.extend(sorted(p.glob("test_*.py")))
            else:
                out.append(p)
        return out
    return sorted(TESTS_DIR.glob("test_*.py"))


def _fixture_kwargs(fn, test_name: str) -> tuple[dict[str, object], list[object]]:
    kwargs: dict[str, object] = {}
    cleanup: list[object] = []
    for param in inspect.signature(fn).parameters:
        if param == "tmp_path":
            kwargs[param] = pathlib.Path(tempfile.mkdtemp(prefix="causalgate_test_"))
        elif param == "monkeypatch":
            mp = _MonkeyPatchShim()
            kwargs[param] = mp
            cleanup.append(mp)
        else:
            raise RuntimeError(f"unsupported fixture '{param}' in {test_name}")
    return kwargs, cleanup


def _cleanup_fixtures(cleanup: Iterable[object]) -> None:
    for item in cleanup:
        undo = getattr(item, "undo", None)
        if callable(undo):
            undo()


def _load_module(path: pathlib.Path):
    module_name = "causalgate_selftest_" + path.stem
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load test module {path.name}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _missing_module_name(exc: BaseException) -> str:
    if isinstance(exc, ModuleNotFoundError):
        return str(getattr(exc, "name", "") or "")
    message = str(exc)
    marker = "No module named '"
    if marker in message:
        return message.split(marker, 1)[1].split("'", 1)[0]
    return ""


def _offline_skippable_import_error(exc: BaseException) -> bool:
    if not OFFLINE_CORE:
        return False
    missing = _missing_module_name(exc).split(".", 1)[0]
    return missing in OFFLINE_SKIP_MODULES


def run(paths: Iterable[pathlib.Path]) -> int:
    sys.path.insert(0, str(ROOT))
    _install_pytest_shim()
    passed = 0
    failed = 0
    skipped_imports = 0

    if OFFLINE_CORE:
        print("CAUSALGATE_OFFLINE_CORE_TESTS=1: missing numpy/pandas/PyYAML import failures will be skipped for core smoke testing.")

    for path in paths:
        rel = path.relative_to(ROOT) if path.is_absolute() and path.is_relative_to(ROOT) else path
        try:
            mod = _load_module(path if path.is_absolute() else ROOT / path)
        except BaseException as exc:
            if _offline_skippable_import_error(exc):
                skipped_imports += 1
                print(f"SKIP_IMPORT_DEP {rel}: {type(exc).__name__}: {exc}")
                continue
            failed += 1
            print(f"IMPORT_FAIL {rel}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=5)
            continue

        for name in sorted(n for n in dir(mod) if n.startswith("test_")):
            fn = getattr(mod, name)
            if not callable(fn):
                continue
            cleanup: list[object] = []
            try:
                kwargs, cleanup = _fixture_kwargs(fn, f"{rel}:{name}")
                fn(**kwargs)
                passed += 1
            except BaseException as exc:
                failed += 1
                print(f"FAIL {rel}:{name}: {type(exc).__name__}: {exc}")
                traceback.print_exc(limit=8)
            finally:
                _cleanup_fixtures(cleanup)

    print(f"CausalGate self-test summary: passed={passed} failed={failed} skipped_imports={skipped_imports}")
    return 1 if failed else 0


if __name__ == "__main__":
    selected = _iter_test_files(sys.argv[1:])
    code = run(selected)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)