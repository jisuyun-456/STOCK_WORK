"""Tests for research/regime_hmm.py — A through G scenarios."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# Skip tests that require hmmlearn if it's not installed (Python 3.14 has no wheel yet)
hmmlearn = pytest.importorskip(
    "hmmlearn",
    reason="hmmlearn not installed — requires C++ build tools on Python 3.14+",
)

from research.regime_hmm import (
    RegimeHMM,
    get_or_train_hmm,
    score_from_regime_prob,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

VALID_REGIMES = {"BULL", "NEUTRAL", "BEAR", "CRISIS"}


def _make_spy_vix(n: int = 600, seed: int = 0) -> tuple[pd.Series, pd.Series]:
    """Generate synthetic SPY / VIX series (n trading days)."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2021-01-04", periods=n)

    # SPY: random walk with slight upward drift
    log_ret = rng.normal(0.0003, 0.01, n)
    spy = pd.Series(np.exp(np.cumsum(log_ret)) * 400, index=dates, name="SPY")

    # VIX: mean-reverting around 20
    vix_raw = 20 + rng.normal(0, 5, n).cumsum() * 0.1
    vix = pd.Series(np.clip(vix_raw, 10, 80), index=dates, name="VIX")

    return spy, vix


def _make_regime_hmm_fitted(n: int = 600, seed: int = 0) -> RegimeHMM:
    spy, vix = _make_spy_vix(n=n, seed=seed)
    hmm = RegimeHMM(min_states=2, max_states=3, n_iter=50, random_state=42)
    hmm.fit(spy, vix)
    return hmm


# ── A. Feature engineering ────────────────────────────────────────────────────


class TestPrepareFeatures:
    def test_shape_and_no_nan(self):
        spy, vix = _make_spy_vix(n=500)
        df = RegimeHMM.prepare_features(spy, vix)
        assert df.shape[1] == 3
        assert not df.isnull().any().any()
        # 21-day rolling window removes first 20 rows + 1 diff row
        assert len(df) <= 500

    def test_columns_present(self):
        spy, vix = _make_spy_vix(n=300)
        df = RegimeHMM.prepare_features(spy, vix)
        assert set(df.columns) == {"ret", "log_vix", "vol21"}

    def test_raises_on_short_series(self):
        spy, vix = _make_spy_vix(n=50)
        with pytest.raises(ValueError, match="Not enough data"):
            RegimeHMM.prepare_features(spy, vix)

    def test_log_vix_always_positive(self):
        spy, vix = _make_spy_vix(n=300)
        df = RegimeHMM.prepare_features(spy, vix)
        assert (df["log_vix"] > 0).all()

    def test_vol21_positive(self):
        spy, vix = _make_spy_vix(n=300)
        df = RegimeHMM.prepare_features(spy, vix)
        assert (df["vol21"] > 0).all()


# ── B. State count selection ──────────────────────────────────────────────────


class TestSelectNStates:
    def test_returns_valid_range(self):
        hmm = _make_regime_hmm_fitted(n=600)
        assert 2 <= hmm.n_states <= 6

    def test_deterministic_with_fixed_seed(self):
        spy, vix = _make_spy_vix(n=600, seed=7)
        hmm1 = RegimeHMM(min_states=2, max_states=4, n_iter=50, random_state=42)
        hmm1.fit(spy, vix)
        hmm2 = RegimeHMM(min_states=2, max_states=4, n_iter=50, random_state=42)
        hmm2.fit(spy, vix)
        assert hmm1.n_states == hmm2.n_states

    def test_training_score_populated(self):
        hmm = _make_regime_hmm_fitted()
        assert "bic" in hmm.training_score
        assert "aic" in hmm.training_score
        assert "log_likelihood" in hmm.training_score
        assert math.isfinite(hmm.training_score["bic"])


# ── C. State → regime mapping ─────────────────────────────────────────────────


class TestMapStatesToRegimes:
    def test_all_labels_within_four_regimes(self):
        hmm = _make_regime_hmm_fitted()
        assert set(hmm.state_to_regime.values()) <= VALID_REGIMES

    def test_crisis_assigned_to_high_vix_state(self):
        """Manually inject a high-VIX state and verify it becomes CRISIS."""
        spy, vix = _make_spy_vix(n=800, seed=1)
        # Spike last 50 days VIX
        vix.iloc[-50:] = 70
        hmm = RegimeHMM(min_states=2, max_states=3, n_iter=50, random_state=42)
        hmm.fit(spy, vix)
        assert "CRISIS" in hmm.state_to_regime.values()

    def test_no_duplicate_labels(self):
        hmm = _make_regime_hmm_fitted(seed=3)
        labels = list(hmm.state_to_regime.values())
        # Each label appears at most once (except NEUTRAL which can be shared
        # across remaining states)
        non_neutral = [l for l in labels if l != "NEUTRAL"]
        assert len(non_neutral) == len(set(non_neutral))


# ── D. Predict ────────────────────────────────────────────────────────────────


class TestPredictCurrent:
    def test_returns_valid_regime_label(self):
        hmm = _make_regime_hmm_fitted()
        spy, vix = _make_spy_vix(n=600)
        regime, meta = hmm.predict_current(spy, vix)
        assert regime in VALID_REGIMES

    def test_metadata_keys_present(self):
        hmm = _make_regime_hmm_fitted()
        spy, vix = _make_spy_vix(n=600)
        _, meta = hmm.predict_current(spy, vix)
        for key in ("most_likely_state", "regime", "regime_prob", "state_probs", "n_states"):
            assert key in meta

    def test_state_probs_sum_to_one(self):
        hmm = _make_regime_hmm_fitted()
        spy, vix = _make_spy_vix(n=600)
        _, meta = hmm.predict_current(spy, vix)
        total = sum(meta["state_probs"].values())
        assert abs(total - 1.0) < 1e-3

    def test_regime_prob_between_0_and_1(self):
        hmm = _make_regime_hmm_fitted()
        spy, vix = _make_spy_vix(n=600)
        _, meta = hmm.predict_current(spy, vix)
        assert 0.0 <= meta["regime_prob"] <= 1.0

    def test_raises_if_not_fitted(self):
        hmm = RegimeHMM()
        spy, vix = _make_spy_vix(n=300)
        with pytest.raises(RuntimeError):
            hmm.predict_current(spy, vix)


# ── E. Cache ──────────────────────────────────────────────────────────────────


class TestCache:
    def test_save_load_roundtrip(self, tmp_path):
        hmm = _make_regime_hmm_fitted()
        cache_file = tmp_path / "hmm_test.pkl"
        hmm.save_cache(cache_file)

        loaded = RegimeHMM.load_cache(cache_file)
        assert loaded is not None
        assert loaded.n_states == hmm.n_states
        assert loaded.state_to_regime == hmm.state_to_regime
        assert loaded.fit_date == hmm.fit_date

    def test_load_returns_none_if_file_missing(self, tmp_path):
        result = RegimeHMM.load_cache(tmp_path / "nonexistent.pkl")
        assert result is None

    def test_load_returns_none_on_version_mismatch(self, tmp_path):
        import joblib

        cache_file = tmp_path / "hmm_bad_version.pkl"
        joblib.dump({"__version__": 999, "model": None}, cache_file)
        result = RegimeHMM.load_cache(cache_file)
        assert result is None

    def test_stale_cache_triggers_refit(self, tmp_path):
        """If cache is >max_age_days old, get_or_train_hmm should attempt refit."""
        hmm = _make_regime_hmm_fitted()
        # Make the fit_date 40 days in the past
        hmm.fit_date = datetime.now(timezone.utc) - timedelta(days=40)
        cache_file = tmp_path / "stale.pkl"
        hmm.save_cache(cache_file)

        refit_called = []

        def fake_download(*args, **kwargs):
            refit_called.append(True)
            # Return a tiny valid df to cause ValueError (too short) →
            # triggers None return safely
            raise RuntimeError("simulated network error")

        with patch("yfinance.download", side_effect=fake_download):
            result = get_or_train_hmm(max_age_days=30, cache_path=cache_file)

        # Refit was attempted (download called)
        assert len(refit_called) == 1
        # Returns None because retraining failed
        assert result is None


# ── F. Fallback ───────────────────────────────────────────────────────────────


class TestFallback:
    def test_get_or_train_hmm_returns_none_on_yfinance_failure(self, tmp_path):
        cache_file = tmp_path / "empty.pkl"  # no cache

        with patch("yfinance.download", side_effect=RuntimeError("network error")):
            result = get_or_train_hmm(max_age_days=30, cache_path=cache_file)

        assert result is None

    def test_get_or_train_hmm_returns_none_on_empty_data(self, tmp_path):
        cache_file = tmp_path / "empty2.pkl"
        empty_df = pd.DataFrame()

        with patch("yfinance.download", return_value=empty_df):
            result = get_or_train_hmm(max_age_days=30, cache_path=cache_file)

        assert result is None

    def test_consensus_fallback_uses_legacy_weights(self, tmp_path):
        """detect_regime_enhanced() should use 0.4/0.3/0.3 when HMM is None."""
        import yfinance as yf_mod

        # Patch get_or_train_hmm to return None
        # Patch yfinance so detect_regime_enhanced can still run
        spy_hist = pd.DataFrame(
            {"Close": [400.0] * 250},
            index=pd.bdate_range("2024-01-02", periods=250),
        )
        vix_hist = pd.DataFrame(
            {"Close": [18.0] * 5},
            index=pd.bdate_range("2025-12-29", periods=5),
        )

        mock_spy_ticker = MagicMock()
        mock_spy_ticker.history.return_value = spy_hist
        mock_vix_ticker = MagicMock()
        mock_vix_ticker.history.return_value = vix_hist

        def fake_ticker(symbol):
            if symbol == "SPY":
                return mock_spy_ticker
            return mock_vix_ticker

        with (
            patch("research.consensus.get_or_train_hmm", return_value=None),
            patch("yfinance.Ticker", side_effect=fake_ticker),
        ):
            from research.consensus import detect_regime_enhanced
            result = detect_regime_enhanced(news_sentiment_score=0.0)

        # Result is a valid RegimeDetection
        assert result.regime in VALID_REGIMES
        # When HMM is None, reasoning should NOT mention HMM
        assert "HMM" not in result.reasoning


# ── G. Backtest vectorized ────────────────────────────────────────────────────
# (added in Step 6 — imported from backtest_core)


class TestDetectRegimeHmmVectorized:
    def test_shape_matches_input(self):
        from scripts.backtest_core import detect_regime_hmm_vectorized

        spy, vix = _make_spy_vix(n=700, seed=5)
        result = detect_regime_hmm_vectorized(spy, vix, refit_every=63, min_train_days=504)
        assert isinstance(result, pd.Series)
        assert len(result) == len(spy)

    def test_all_values_are_valid_regimes(self):
        from scripts.backtest_core import detect_regime_hmm_vectorized

        spy, vix = _make_spy_vix(n=700, seed=5)
        result = detect_regime_hmm_vectorized(spy, vix, refit_every=63, min_train_days=504)
        assert set(result.unique()) <= VALID_REGIMES

    def test_no_lookahead_bias(self):
        """regime at day 600 must equal result from fit(spy[:600], vix[:600])."""
        from scripts.backtest_core import detect_regime_hmm_vectorized

        n_total = 700
        cutoff = 600
        spy, vix = _make_spy_vix(n=n_total, seed=9)

        # Full series result
        full_result = detect_regime_hmm_vectorized(
            spy, vix, refit_every=63, min_train_days=504
        )
        regime_at_cutoff = full_result.iloc[cutoff - 1]

        # Manually fit on spy[:cutoff] only
        # The last refit before cutoff should happen at the nearest multiple of 63
        last_refit_idx = ((cutoff - 504) // 63) * 63 + 504
        if last_refit_idx > cutoff:
            last_refit_idx = 504  # fallback to first refit

        hmm = RegimeHMM(min_states=2, max_states=3, n_iter=50, random_state=42)
        hmm.fit(spy.iloc[:last_refit_idx], vix.iloc[:last_refit_idx])
        seq = hmm.predict_sequence(
            spy.iloc[:last_refit_idx], vix.iloc[:last_refit_idx]
        )
        # Map the last predicted regime from the isolated fit
        isolated_regime = seq.iloc[-1]

        assert regime_at_cutoff == isolated_regime


# ── score_from_regime_prob ────────────────────────────────────────────────────


class TestScoreFromRegimeProb:
    def test_bull_gives_score_1(self):
        probs = {"BULL": 1.0}
        assert score_from_regime_prob(probs, {}) == 1.0

    def test_crisis_gives_score_0(self):
        probs = {"CRISIS": 1.0}
        assert score_from_regime_prob(probs, {}) == 0.0

    def test_mixed_probs_weighted(self):
        probs = {"BULL": 0.5, "CRISIS": 0.5}
        # 0.5 * 1.0 + 0.5 * 0.0 = 0.5
        assert abs(score_from_regime_prob(probs, {}) - 0.5) < 1e-4

    def test_neutral_gives_0_6(self):
        probs = {"NEUTRAL": 1.0}
        assert abs(score_from_regime_prob(probs, {}) - 0.6) < 1e-4
