"""Auto-tracing for observability."""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import inspect
import logging
import sys
import sysconfig
import threading
from types import ModuleType
from typing import Any

_log = logging.getLogger(__name__)
_patched_modules: set[int] = set()
_patched_modules_lock = threading.Lock()
_active = False
_stdlib_prefixes: tuple[str, ...] = ()
_SKIP_PATH_MARKERS = frozenset({"site-packages", "dist-packages"})


def _is_project_path(path: str | None) -> bool:
    if not path or path.startswith("<"):
        return False
    if any(marker in path for marker in _SKIP_PATH_MARKERS):
        return False
    if _stdlib_prefixes and path.startswith(_stdlib_prefixes):
        return False
    return True


def _is_traced(obj: Any) -> bool:
    return bool(getattr(obj, "__traced__", False))


def _wrap_member(obj: Any, traced):
    if inspect.isfunction(obj) and not _is_traced(obj):
        return traced(obj)
    if isinstance(obj, staticmethod):
        inner = obj.__func__
        if inspect.isfunction(inner) and not _is_traced(inner):
            return staticmethod(traced(inner))
    if isinstance(obj, classmethod):
        inner = obj.__func__
        if inspect.isfunction(inner) and not _is_traced(inner):
            return classmethod(traced(inner))
    return None


def _patch_module(module: ModuleType) -> None:
    from temporal.observability import traced

    mod_id = id(module)
    with _patched_modules_lock:
        if mod_id in _patched_modules:
            return
        _patched_modules.add(mod_id)

    mod_name = getattr(module, "__name__", "")

    for attr_name, obj in list(vars(module).items()):
        if attr_name.startswith("__") and attr_name.endswith("__"):
            continue

        if obj is None or getattr(obj, "__module__", None) != mod_name:
            continue

        if inspect.isfunction(obj) and not _is_traced(obj):
            setattr(module, attr_name, traced(obj))
            continue

        if inspect.isclass(obj):
            for name, member in vars(obj).items():
                if name.startswith("__") and name.endswith("__"):
                    continue
                wrapped = _wrap_member(member, traced)
                if wrapped is not None:
                    setattr(obj, name, wrapped)

    _log.debug("Auto-traced module %s", mod_name)


class _TracingLoader(importlib.abc.Loader):
    """Wraps the real loader and calls _patch_module after exec_module."""

    def __init__(self, inner: importlib.abc.Loader) -> None:
        self._inner = inner

    def create_module(self, spec):
        if hasattr(self._inner, "create_module"):
            return self._inner.create_module(spec)
        return None

    def exec_module(self, module: ModuleType) -> None:
        self._inner.exec_module(module)
        _patch_module(module)


class _TracingFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        # Don't trace the tracing infrastructure itself.
        if fullname == "temporal" or fullname.startswith("temporal."):
            return None

        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.loader is None:
            return None
        if not _is_project_path(spec.origin):
            return None

        spec.loader = _TracingLoader(spec.loader)
        return spec


def _is_project_module(module: ModuleType | None) -> bool:
    if module is None:
        return False

    mod_name = getattr(module, "__name__", "") or ""
    if mod_name == "temporal" or mod_name.startswith("temporal."):
        return False
    return _is_project_path(getattr(module, "__file__", None))


# ---- Public entry point ----


def enable_auto_tracing() -> None:
    """Install the import hook and instrument already-imported project modules."""
    global _active, _stdlib_prefixes
    if _active:
        return

    paths = sysconfig.get_paths()
    _stdlib_prefixes = tuple(
        paths[key] for key in ("stdlib", "platstdlib") if paths.get(key)
    )

    sys.meta_path.insert(0, _TracingFinder())
    _active = True

    for mod in list(sys.modules.values()):
        if _is_project_module(mod):
            _patch_module(mod)

    _log.info("Auto-tracing enabled")
