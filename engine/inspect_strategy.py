#!/usr/bin/env python3
"""
inspect_strategy.py — Extract metadata from an uploaded TrustyStrategy file.

Usage:
    python3 inspect_strategy.py <path/to/strategy_file.py>

Output (stdout): JSON object with keys:
    name        : str   — strategy identifier (from strategy.name())
    symbols     : list  — universe() tickers
    lookback    : int   — max_lookback_period()
    params      : dict  — config field names → {default, type, description}
    error       : str   — set only on failure (all other keys absent)

The Rust API server calls this script, reads its stdout, and returns the
result directly to the dashboard.  Stderr is forwarded to the server log.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import sys
import traceback
from dataclasses import fields as dc_fields
from pathlib import Path
from typing import Any


def _py_type_tag(annotation: Any) -> str:
    """Convert a Python type annotation to a short dashboard-friendly string."""
    if annotation is inspect.Parameter.empty:
        return "any"
    name = getattr(annotation, "__name__", None) or str(annotation)
    return {"int": "int", "float": "float", "bool": "bool", "str": "text"}.get(name, "float")


def _extract_config_params(config_cls: type) -> dict:
    """
    Pull every dataclass field from a StrategyConfig subclass.
    Returns {field_name: {default, type, description}}.
    """
    params: dict = {}
    try:
        for f in dc_fields(config_cls):
            # Skip the inherited circuit-breaker field — not user-facing.
            if f.name == "consecutive_bad_bars_threshold":
                continue
            default = f.default if f.default is not f.default_factory else None  # type: ignore[misc]
            if default is inspect.Parameter.empty:
                default = None
            # Try to coerce to a plain Python scalar (not a dataclasses sentinel).
            try:
                json.dumps(default)
            except (TypeError, ValueError):
                default = None
            params[f.name] = {
                "default": default,
                "type": _py_type_tag(f.type),
                "description": f.metadata.get("description", ""),
            }
    except Exception:
        pass
    return params


def inspect_file(path: str) -> dict:
    """Load the strategy file and return its metadata as a plain dict."""
    p = Path(path).resolve()
    if not p.exists():
        return {"error": f"File not found: {path}"}

    # ---------------------------------------------------------------------------
    # Dynamically load the module from the given file path.
    # We need sys.path to include the workspace root so that
    # `from bridge.strategy_interface import …` resolves correctly.
    # ---------------------------------------------------------------------------
    workspace_root = p.parent.parent  # python_strategies/strategies/ → root
    # Try two common layouts: strategy is directly in python_strategies/strategies/
    # or in the workspace root's python_strategies/ folder.
    candidates = [
        p.parent.parent,   # .../python_strategies/strategies/../..  (workspace root)
        p.parent.parent.parent,  # one level deeper
    ]
    for candidate in candidates:
        bridge_check = candidate / "bridge" / "strategy_interface.py"
        if bridge_check.exists():
            workspace_root = candidate
            break

    if str(workspace_root) not in sys.path:
        sys.path.insert(0, str(workspace_root))

    spec = importlib.util.spec_from_file_location("_uploaded_strategy_", str(p))
    if spec is None or spec.loader is None:
        return {"error": "Could not create module spec for file"}

    mod = importlib.util.module_from_spec(spec)
    # Register in sys.modules BEFORE exec_module so that @dataclass and other
    # decorators that look up the module via sys.modules[cls.__module__] work.
    sys.modules["_uploaded_strategy_"] = mod
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except Exception as exc:
        sys.modules.pop("_uploaded_strategy_", None)
        return {"error": f"Import error: {exc}\n{traceback.format_exc()}"}
    finally:
        sys.modules.pop("_uploaded_strategy_", None)

    # ---------------------------------------------------------------------------
    # Find the TrustyStrategy subclass(es) in the module.
    # ---------------------------------------------------------------------------
    try:
        from bridge.strategy_interface import TrustyStrategy
    except ImportError as exc:
        return {"error": f"Cannot import TrustyStrategy from bridge: {exc}"}

    strategy_classes = [
        obj
        for obj in vars(mod).values()
        if isinstance(obj, type)
        and issubclass(obj, TrustyStrategy)
        and obj is not TrustyStrategy
    ]

    if not strategy_classes:
        return {"error": "No TrustyStrategy subclass found in the uploaded file"}

    # Use the first one (or the last one — typically the main strategy, not inner helpers).
    strategy_cls = strategy_classes[-1]

    # ---------------------------------------------------------------------------
    # Find the Config dataclass (StrategyConfig subclass).
    # ---------------------------------------------------------------------------
    try:
        from bridge.strategy_interface import StrategyConfig
    except ImportError:
        StrategyConfig = None  # type: ignore[assignment]

    config_classes = []
    if StrategyConfig is not None:
        config_classes = [
            obj
            for obj in vars(mod).values()
            if isinstance(obj, type)
            and issubclass(obj, StrategyConfig)
            and obj is not StrategyConfig
        ]

    params: dict = {}
    config_cls = config_classes[-1] if config_classes else None
    if config_cls is not None:
        params = _extract_config_params(config_cls)

    # ---------------------------------------------------------------------------
    # Instantiate the strategy to call universe() and max_lookback_period().
    # ---------------------------------------------------------------------------
    try:
        if config_cls is not None:
            instance = strategy_cls(config_cls())
        else:
            instance = strategy_cls()  # type: ignore[call-arg]
    except Exception as exc:
        return {"error": f"Cannot instantiate strategy: {exc}\n{traceback.format_exc()}"}

    try:
        symbols = instance.universe()
    except Exception as exc:
        return {"error": f"universe() raised: {exc}"}

    try:
        rate_syms = instance.rate_symbols()
    except Exception:
        rate_syms = []

    try:
        lookback = instance.max_lookback_period()
    except Exception as exc:
        lookback = 0

    try:
        name = instance.name()
    except Exception:
        name = strategy_cls.__name__

    try:
        rate_syms = instance.rate_symbols()
    except Exception:
        rate_syms = []

    return {
        "name": name,
        "class_name": strategy_cls.__name__,
        "symbols": symbols,
        "rate_symbols": rate_syms,
        "lookback": lookback,
        "params": params,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: inspect_strategy.py <path>"}))
        sys.exit(1)

    result = inspect_file(sys.argv[1])
    print(json.dumps(result))
