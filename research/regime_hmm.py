"""HMM-based regime detection using hmmlearn GaussianHMM.

Public API:
    get_or_train_hmm(max_age_days=30) -> RegimeHMM | None
    score_from_regime_prob(state_probs, state_to_regime) -> float
    RegimeHMM  (class)
"""
from __future__ import annotations

import logging
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Cache path ────────────────────────────────────────────────────────────────

_DEFAULT_CACHE = Path(__file__).parent.parent / "state" / "hmm_model_cache.pkl"
_CACHE_VERSION = 2  # bump when breaking schema changes

# ── Regime score mapping (0~1 continuous) ────────────────────────────────────

_REGIME_SCORES: dict[str, float] = {
    "EUPHORIA": 1.0,  # 과매수 — BULL과 동일 연속 점수 (HMM은 RSI 미포함)
    "BULL": 1.0,
    "NEUTRAL": 0.6,
    "BEAR": 0.25,
    "CRISIS": 0.0,
}


# ── RegimeHMM class ───────────────────────────────────────────────────────────


class RegimeHMM:
    """GaussianHMM wrapper for 4-regime market detection.

    Features (3-dim):
        - spy_log_return  : daily log return of SPY
        - log_vix         : np.log1p(VIX close)
        - spy_vol_21d     : 21-day rolling std of log returns

    States are mapped to BULL/NEUTRAL/BEAR/CRISIS via heuristic
    ordering of emission means (VIX level + return drift + volatility).
    """

    def __init__(
        self,
        min_states: int = 2,
        max_states: int = 6,
        feature_window: int = 756,
        covariance_type: str = "full",
        n_iter: int = 200,
        random_state: int = 42,
    ) -> None:
        self.min_states = min_states
        self.max_states = max_states
        self.feature_window = feature_window
        self.covariance_type = covariance_type
        self.n_iter = n_iter
        self.random_state = random_state

        self.model = None          # GaussianHMM
        self.scaler = None         # StandardScaler
        self.n_states: Optional[int] = None
        self.state_to_regime: dict[int, str] = {}
        self.fit_date: Optional[datetime] = None
        self.training_score: dict = {}

    # ── Feature engineering ───────────────────────────────────────────────────

    @staticmethod
    def prepare_features(
        spy_close: pd.Series,
        vix_close: pd.Series,
    ) -> pd.DataFrame:
        """Build (ret, log_vix, vol21) feature DataFrame from price series.

        Raises:
            ValueError: if aligned result has fewer than 252 rows.
        """
        spy = spy_close.copy()
        vix = vix_close.copy()

        # Align indices
        common_idx = spy.index.intersection(vix.index)
        spy = spy.loc[common_idx]
        vix = vix.loc[common_idx]

        ret = np.log(spy).diff()
        log_vix = np.log1p(vix)
        vol21 = ret.rolling(21).std()

        df = pd.DataFrame({"ret": ret, "log_vix": log_vix, "vol21": vol21}).dropna()

        if len(df) < 252:
            raise ValueError(
                f"Not enough data after feature engineering: {len(df)} rows (need ≥252)"
            )
        return df

    # ── BIC-based state selection ─────────────────────────────────────────────

    def _select_n_states(self, X: np.ndarray):
        """Try min_states..max_states; select by BIC. Return (n, model)."""
        try:
            from hmmlearn.hmm import GaussianHMM
        except ImportError as e:
            raise ImportError("hmmlearn is required: pip install hmmlearn>=0.3.0") from e

        n_samples, n_features = X.shape
        best_bic = np.inf
        best_k = None
        best_model = None

        for k in range(self.min_states, self.max_states + 1):
            try:
                model = GaussianHMM(
                    n_components=k,
                    covariance_type=self.covariance_type,
                    n_iter=self.n_iter,
                    random_state=self.random_state,
                    min_covar=1e-3,
                )
                model.fit(X)

                if not model.monitor_.converged:
                    logger.debug("HMM k=%d did not converge, skipping", k)
                    continue

                log_lik = model.score(X)

                # num_params: transmat (k*(k-1)) + means (k*d) + covars + startprob (k-1)
                if self.covariance_type == "full":
                    cov_params = k * n_features * (n_features + 1) // 2
                elif self.covariance_type == "diag":
                    cov_params = k * n_features
                else:
                    cov_params = k * n_features
                num_params = k * (k - 1) + k * n_features + cov_params + (k - 1)

                bic = -2 * log_lik + math.log(n_samples) * num_params
                aic = -2 * log_lik + 2 * num_params

                logger.debug("k=%d  BIC=%.1f  AIC=%.1f  log_lik=%.1f", k, bic, aic, log_lik)

                if bic < best_bic:
                    best_bic = bic
                    best_k = k
                    best_model = model
                    self.training_score = {
                        "n_states": k,
                        "bic": round(bic, 2),
                        "aic": round(aic, 2),
                        "log_likelihood": round(log_lik, 2),
                    }

            except Exception as exc:
                logger.debug("HMM k=%d fit error: %s", k, exc)
                continue

        if best_model is None:
            raise ValueError("All HMM candidates failed to converge")

        return best_k, best_model

    # ── State → regime label mapping ─────────────────────────────────────────

    def _map_states_to_regimes(self, model) -> dict[int, str]:
        """Map HMM state indices to BULL/NEUTRAL/BEAR/CRISIS labels.

        Heuristic ordering based on emission means:
            1. Highest log_vix mean  (+ vol)  → CRISIS
            2. Most negative ret mean          → BEAR
            3. Positive ret + lowest VIX mean  → BULL
            4. Remainder                       → NEUTRAL
        """
        from sklearn.preprocessing import StandardScaler  # scaler already fit

        means = model.means_  # shape (n_states, 3): [ret, log_vix, vol21]
        n = model.n_components

        # Inverse-transform means to original scale for interpretable thresholds
        # scaler is already fit at this point (self.scaler)
        means_orig = self.scaler.inverse_transform(means)
        # means_orig columns: [ret, log_vix, vol21]
        # Recover actual VIX: np.expm1(log_vix)
        vix_means = np.expm1(means_orig[:, 1])
        ret_means = means_orig[:, 0]
        vol_means = means_orig[:, 2]

        state_to_regime: dict[int, str] = {}
        assigned: set[int] = set()
        used_labels: set[str] = set()

        # 1. CRISIS: highest VIX mean
        crisis_state = int(np.argmax(vix_means))
        state_to_regime[crisis_state] = "CRISIS"
        assigned.add(crisis_state)
        used_labels.add("CRISIS")

        # 2. BEAR: most negative ret mean among remaining
        remaining = [s for s in range(n) if s not in assigned]
        if remaining:
            bear_state = min(remaining, key=lambda s: ret_means[s])
            if ret_means[bear_state] < 0:
                state_to_regime[bear_state] = "BEAR"
                assigned.add(bear_state)
                used_labels.add("BEAR")

        # 3. BULL: positive ret + lowest VIX among remaining
        remaining = [s for s in range(n) if s not in assigned]
        if remaining:
            bull_candidates = [s for s in remaining if ret_means[s] >= 0]
            if bull_candidates:
                bull_state = min(bull_candidates, key=lambda s: vix_means[s])
            else:
                # fallback: best ret among remaining
                bull_state = max(remaining, key=lambda s: ret_means[s])
            state_to_regime[bull_state] = "BULL"
            assigned.add(bull_state)
            used_labels.add("BULL")

        # 4. NEUTRAL: all remaining
        for s in range(n):
            if s not in assigned:
                state_to_regime[s] = "NEUTRAL"

        logger.info("HMM state→regime map: %s  (VIX means: %s)", state_to_regime, np.round(vix_means, 1))
        return state_to_regime

    # ── fit ───────────────────────────────────────────────────────────────────

    def fit(self, spy_series: pd.Series, vix_series: pd.Series) -> None:
        """Train HMM on historical SPY + VIX data and cache the model."""
        from sklearn.preprocessing import StandardScaler

        df = self.prepare_features(spy_series, vix_series)

        # Apply feature_window (most recent rows)
        if len(df) > self.feature_window:
            df = df.iloc[-self.feature_window:]

        X_raw = df.values.astype(float)

        self.scaler = StandardScaler()
        X = self.scaler.fit_transform(X_raw)

        n_states, model = self._select_n_states(X)
        self.model = model
        self.n_states = n_states
        self.state_to_regime = self._map_states_to_regimes(model)
        self.fit_date = datetime.now(timezone.utc)

        logger.info(
            "RegimeHMM fit complete: n_states=%d  map=%s  BIC=%.1f",
            n_states,
            self.state_to_regime,
            self.training_score.get("bic", float("nan")),
        )

    # ── predict ──────────────────────────────────────────────────────────────

    def predict_current(
        self, spy_series: pd.Series, vix_series: pd.Series
    ) -> tuple[str, dict]:
        """Predict current regime from recent price data.

        Returns:
            (regime_label, metadata_dict)
        """
        if self.model is None or self.scaler is None:
            raise RuntimeError("RegimeHMM.fit() must be called before predict_current()")

        df = self.prepare_features(spy_series, vix_series)
        X_raw = df.values.astype(float)
        X = self.scaler.transform(X_raw)

        # predict_proba over the full sequence; use the last row
        posteriors = self.model.predict_proba(X)  # shape (T, n_states)
        last_posterior = posteriors[-1]

        most_likely_state = int(np.argmax(last_posterior))
        regime = self.state_to_regime.get(most_likely_state, "NEUTRAL")

        state_probs = {
            self.state_to_regime.get(s, f"state_{s}"): round(float(p), 4)
            for s, p in enumerate(last_posterior)
        }

        metadata = {
            "most_likely_state": most_likely_state,
            "regime": regime,
            "regime_prob": round(float(last_posterior[most_likely_state]), 4),
            "state_probs": state_probs,
            "n_states": self.n_states,
            "fit_date": self.fit_date.isoformat() if self.fit_date else None,
            "training_score": self.training_score,
        }
        return regime, metadata

    def predict_sequence(
        self, spy_series: pd.Series, vix_series: pd.Series
    ) -> pd.Series:
        """Predict regime for every row in the given series.

        Returns a pd.Series indexed by the feature DataFrame's index.
        Used for vectorized backtest application.
        """
        if self.model is None or self.scaler is None:
            raise RuntimeError("RegimeHMM.fit() must be called before predict_sequence()")

        df = self.prepare_features(spy_series, vix_series)
        X_raw = df.values.astype(float)
        X = self.scaler.transform(X_raw)

        states = self.model.predict(X)
        regimes = pd.Series(
            [self.state_to_regime.get(int(s), "NEUTRAL") for s in states],
            index=df.index,
        )
        return regimes

    # ── cache ─────────────────────────────────────────────────────────────────

    def save_cache(self, path: str | Path = _DEFAULT_CACHE) -> None:
        """Persist model to disk via joblib."""
        import joblib

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "__version__": _CACHE_VERSION,
            "model": self.model,
            "scaler": self.scaler,
            "n_states": self.n_states,
            "state_to_regime": self.state_to_regime,
            "fit_date": self.fit_date,
            "training_score": self.training_score,
            "min_states": self.min_states,
            "max_states": self.max_states,
        }
        joblib.dump(payload, path)
        logger.info("RegimeHMM cache saved to %s", path)

    @classmethod
    def load_cache(cls, path: str | Path = _DEFAULT_CACHE) -> Optional["RegimeHMM"]:
        """Load model from disk. Returns None on any failure."""
        import joblib

        path = Path(path)
        if not path.exists():
            return None
        try:
            payload = joblib.load(path)
            if payload.get("__version__") != _CACHE_VERSION:
                logger.warning("HMM cache version mismatch — discarding")
                return None

            obj = cls(
                min_states=payload.get("min_states", 2),
                max_states=payload.get("max_states", 6),
            )
            obj.model = payload["model"]
            obj.scaler = payload["scaler"]
            obj.n_states = payload["n_states"]
            obj.state_to_regime = payload["state_to_regime"]
            obj.fit_date = payload["fit_date"]
            obj.training_score = payload.get("training_score", {})
            return obj
        except Exception as exc:
            logger.warning("Failed to load HMM cache: %s", exc)
            return None


# ── Module-level helpers ──────────────────────────────────────────────────────


def get_or_train_hmm(
    max_age_days: int = 30,
    cache_path: str | Path = _DEFAULT_CACHE,
) -> Optional[RegimeHMM]:
    """Return a trained RegimeHMM, loading from cache or retraining.

    Returns None on any failure so callers can fall back to rule-based regime.
    """
    try:
        cached = RegimeHMM.load_cache(cache_path)
        if cached is not None and cached.fit_date is not None:
            age = (datetime.now(timezone.utc) - cached.fit_date).days
            if age < max_age_days:
                logger.info("Using cached HMM model (age=%d days)", age)
                return cached
            logger.info("HMM cache is %d days old (max=%d) — retraining", age, max_age_days)

        return _retrain_and_cache(cache_path)

    except Exception as exc:
        logger.warning("get_or_train_hmm failed: %s — falling back to rule-based", exc)
        return None


def _retrain_and_cache(cache_path: str | Path) -> Optional[RegimeHMM]:
    """Download 5y SPY+VIX, fit RegimeHMM, save cache. Returns None on failure."""
    try:
        import yfinance as yf

        logger.info("Downloading 5y SPY+VIX for HMM training…")
        raw = yf.download(["SPY", "^VIX"], period="5y", progress=False, auto_adjust=True)

        if raw.empty:
            logger.warning("yfinance returned empty data for HMM training")
            return None

        # Handle multi-level columns: (field, ticker)
        if isinstance(raw.columns, pd.MultiIndex):
            spy_close = raw["Close"]["SPY"].dropna()
            vix_close = raw["Close"]["^VIX"].dropna()
        else:
            # MultiIndex 없음 = SPY 또는 VIX 다운로드 실패
            # 오염된 데이터로 HMM 재학습하지 않고 안전하게 스킵
            logger.warning("HMM: VIX 또는 SPY 다운로드 실패 (non-MultiIndex 결과) — HMM 재학습 스킵")
            return None

        hmm = RegimeHMM()
        hmm.fit(spy_close, vix_close)
        hmm.save_cache(cache_path)
        return hmm

    except Exception as exc:
        logger.warning("HMM retraining failed: %s", exc)
        return None


def score_from_regime_prob(
    state_probs: dict[str, float],
    state_to_regime: dict[int, str],  # kept for API symmetry, unused internally
) -> float:
    """Convert regime probability dict to continuous 0~1 composite score.

    state_probs keys are regime labels (e.g. "BULL", "CRISIS").
    Weighted by _REGIME_SCORES mapping.
    """
    total = 0.0
    for label, prob in state_probs.items():
        total += prob * _REGIME_SCORES.get(label, 0.5)
    return round(float(total), 4)
