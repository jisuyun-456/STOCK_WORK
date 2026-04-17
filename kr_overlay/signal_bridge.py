"""Bidirectional drift detection and state tracking for the KR overlay.

SignalBridge persists a rolling history of US↔KR adjustments to state/
and warns when the overlay is consistently pushing in one direction
(potential model drift or a regime that's been stuck for too long).
"""
import json
import logging
from datetime import datetime
from pathlib import Path

_logger = logging.getLogger("kr_overlay.signal_bridge")

_STATE_FILE = Path("state/kr_overlay_state.json")
_HISTORY_LIMIT = 30
_DRIFT_WINDOW = 10
_DRIFT_THRESHOLD = 8   # ≥ 8 corrections in last 10 entries → warn


class SignalBridge:
    """Records us↔kr overlay decisions and detects persistent drift."""

    def __init__(self) -> None:
        self._state = self._load_state()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_us_to_kr(self, original: str, corrected: str, bias: dict) -> None:
        """Persist a US→KR regime correction event."""
        entry = {
            "ts": datetime.now().isoformat(),
            "original": original,
            "corrected": corrected,
            "bias": bias,
        }
        self._state["us_to_kr_history"].append(entry)
        self._state["us_to_kr_history"] = (
            self._state["us_to_kr_history"][-_HISTORY_LIMIT:]
        )
        self._check_drift("us_to_kr")
        self._save_state()

    def record_kr_to_us(self, adjustments_count: int, total_signals: int) -> None:
        """Persist a KR→US signal adjustment event."""
        entry = {
            "ts": datetime.now().isoformat(),
            "adjusted": adjustments_count,
            "total": total_signals,
        }
        self._state["kr_to_us_history"].append(entry)
        self._state["kr_to_us_history"] = (
            self._state["kr_to_us_history"][-_HISTORY_LIMIT:]
        )
        self._check_drift("kr_to_us")
        self._save_state()

    def get_drift_warnings(self) -> list[dict]:
        """Return all accumulated drift warnings."""
        return self._state.get("drift_warnings", [])

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _check_drift(self, direction: str) -> None:
        """Warn if the overlay is consistently adjusting in one direction."""
        history = self._state.get(f"{direction}_history", [])[-_DRIFT_WINDOW:]
        if len(history) < 5:
            return  # not enough data

        if direction == "us_to_kr":
            downgrades = sum(
                1 for h in history if h.get("original") != h.get("corrected")
            )
            if downgrades >= _DRIFT_THRESHOLD:
                warning = (
                    f"DRIFT: us_to_kr has downgraded KR regime "
                    f"{downgrades}/{len(history)} times"
                )
                _logger.warning(warning)
                self._state.setdefault("drift_warnings", []).append(
                    {"ts": datetime.now().isoformat(), "warning": warning}
                )

        elif direction == "kr_to_us":
            high_adjust = sum(
                1 for h in history
                if h.get("total", 1) > 0
                and h.get("adjusted", 0) / h.get("total", 1) > 0.5
            )
            if high_adjust >= _DRIFT_THRESHOLD:
                warning = (
                    f"DRIFT: kr_to_us adjusted >50% of signals in "
                    f"{high_adjust}/{len(history)} recent runs"
                )
                _logger.warning(warning)
                self._state.setdefault("drift_warnings", []).append(
                    {"ts": datetime.now().isoformat(), "warning": warning}
                )

    def _load_state(self) -> dict:
        if _STATE_FILE.exists():
            try:
                return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
            except Exception as exc:
                _logger.warning("Failed to load kr_overlay_state: %s", exc)
        return {
            "us_to_kr_history": [],
            "kr_to_us_history": [],
            "drift_warnings": [],
        }

    def _save_state(self) -> None:
        try:
            _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            _STATE_FILE.write_text(
                json.dumps(self._state, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            _logger.warning("Failed to save kr_overlay_state: %s", exc)
