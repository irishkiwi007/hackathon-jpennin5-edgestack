"""bridge — the strategy contract only.

The container's bridge/__init__.py also exports the QuantConnect shim
(rust_bridge_algorithm); EdgeStack borrows just the isomorphic interface, so this
package exposes strategy_interface and nothing else (engine/BORROWED.md).
"""
from bridge.strategy_interface import BarSnapshot, StrategyConfig, TrustyStrategy  # noqa: F401
