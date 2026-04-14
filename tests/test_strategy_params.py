"""strategy_params.json 파라미터 → 전략 클래스 반영 검증 테스트."""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import config.loader as _loader


def _patch_config(overrides: dict):
    """테스트용 config 패치 헬퍼."""
    base = json.loads(
        (Path(__file__).parent.parent / "config/strategy_params.json").read_text(
            encoding="utf-8"
        )
    )
    for section, vals in overrides.items():
        base[section].update(vals)
    _loader._cache = base
    return base


# ── MomentumStrategy ─────────────────────────────────────────────────────────

def test_momentum_reads_max_positions():
    _patch_config({"momentum": {"max_positions": 5}})
    from importlib import reload
    import strategies.momentum as m
    reload(m)
    strat = m.MomentumStrategy()
    assert strat.max_positions == 5, f"expected 5, got {strat.max_positions}"
    _loader.reload_strategy_params()


def test_momentum_reads_stop_loss():
    _patch_config({"momentum": {"stop_loss_pct": 0.07}})
    from importlib import reload
    import strategies.momentum as m
    reload(m)
    strat = m.MomentumStrategy()
    assert strat.stop_loss_pct == 0.07, f"expected 0.07, got {strat.stop_loss_pct}"
    _loader.reload_strategy_params()


def test_momentum_reads_position_pct():
    _patch_config({"momentum": {"position_pct": 0.15}})
    from importlib import reload
    import strategies.momentum as m
    reload(m)
    strat = m.MomentumStrategy()
    assert strat.position_pct == 0.15, f"expected 0.15, got {strat.position_pct}"
    _loader.reload_strategy_params()


# ── QuantFactorStrategy ───────────────────────────────────────────────────────

def test_qnt_reads_max_positions():
    _patch_config({"quant_factor": {"max_positions": 10}})
    from importlib import reload
    import strategies.quant_factor as q
    reload(q)
    strat = q.QuantFactorStrategy()
    assert strat.max_positions == 10, f"expected 10, got {strat.max_positions}"
    _loader.reload_strategy_params()


def test_qnt_min_composite_score_filters():
    """min_composite_score=0.45 설정 시 낮은 스코어 종목이 제외되는지 확인."""
    _patch_config({"quant_factor": {"min_composite_score": 0.45, "max_positions": 20}})
    from importlib import reload
    import strategies.quant_factor as q
    reload(q)
    strat = q.QuantFactorStrategy()
    assert strat.min_composite_score == 0.45, f"expected 0.45, got {strat.min_composite_score}"
    # 직접 필터 로직 검증
    scores = {"A": 0.76, "B": 0.33, "C": 0.22, "D": 0.10}
    filtered = {k: v for k, v in scores.items() if v >= strat.min_composite_score}
    assert set(filtered.keys()) == {"A", "B"}, f"unexpected: {filtered}"
    _loader.reload_strategy_params()


# ── ValueQualityStrategy ─────────────────────────────────────────────────────

def test_val_reads_max_positions():
    _patch_config({"value_quality": {"max_positions": 5}})
    from importlib import reload
    import strategies.value_quality as v
    reload(v)
    strat = v.ValueQualityStrategy()
    assert strat.max_positions == 5, f"expected 5, got {strat.max_positions}"
    _loader.reload_strategy_params()


def test_val_reads_pe_threshold():
    _patch_config({"value_quality": {"pe_threshold_neutral": 18}})
    from importlib import reload
    import strategies.value_quality as v
    reload(v)
    strat = v.ValueQualityStrategy()
    assert strat.pe_threshold_neutral == 18, f"expected 18, got {strat.pe_threshold_neutral}"
    _loader.reload_strategy_params()
