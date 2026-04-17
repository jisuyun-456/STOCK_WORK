"""KR Backtest scenario definitions.

Simple data module — no external dependencies.
Each scenario defines a date range and optional metadata for replay testing.
"""
from typing import Any

SCENARIOS: dict[str, dict[str, Any]] = {
    "semiconductor_rally_2024": {
        "start": "2024-01-01",
        "end": "2024-12-31",
        "description": "2024 반도체 랠리 재생",
        "expected_regime_transitions": ["BEAR", "NEUTRAL", "BULL"],
    },
    "inflation_shock_2022": {
        "start": "2022-01-01",
        "end": "2022-12-31",
        "description": "2022 인플레 쇼크 재생",
        "expected_regime_transitions": ["BEAR", "CRISIS"],
    },
    "default_16m": {
        "start": "2025-01-01",
        "end": "2026-04-17",
        "description": "최근 16개월 재생 (기본)",
    },
}


def get_scenario(name: str) -> dict[str, Any]:
    """Return scenario dict by name. Raises KeyError if not found."""
    if name not in SCENARIOS:
        raise KeyError(f"Unknown scenario: {name!r}. Available: {list(SCENARIOS.keys())}")
    return SCENARIOS[name]


def list_scenarios() -> list[str]:
    """Return list of all scenario names."""
    return list(SCENARIOS.keys())
