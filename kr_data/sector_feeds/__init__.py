"""
kr_data.sector_feeds — 8 sector feed modules for Korean market analysis.

Sectors: semiconductor, battery, bio, shipbuilding, chemical, auto, content, finance.
Each module exposes: fetch_snapshot(), compute_sector_score(), fetch_historical().
"""
from kr_data.sector_feeds import battery  # noqa: F401 — needed for patch.object in tests
from kr_data.sector_feeds.semiconductor import (
    fetch_snapshot as semiconductor_snapshot,
    compute_sector_score as semiconductor_score,
)
from kr_data.sector_feeds.battery import (
    fetch_snapshot as battery_snapshot,
    compute_sector_score as battery_score,
)
from kr_data.sector_feeds.bio import (
    fetch_snapshot as bio_snapshot,
    compute_sector_score as bio_score,
)
from kr_data.sector_feeds.shipbuilding import (
    fetch_snapshot as shipbuilding_snapshot,
    compute_sector_score as shipbuilding_score,
)
from kr_data.sector_feeds.chemical import (
    fetch_snapshot as chemical_snapshot,
    compute_sector_score as chemical_score,
)
from kr_data.sector_feeds.auto import (
    fetch_snapshot as auto_snapshot,
    compute_sector_score as auto_score,
)
from kr_data.sector_feeds.content import (
    fetch_snapshot as content_snapshot,
    compute_sector_score as content_score,
)
from kr_data.sector_feeds.finance import (
    fetch_snapshot as finance_snapshot,
    compute_sector_score as finance_score,
)

ALL_SECTORS = [
    "semiconductor",
    "battery",
    "bio",
    "shipbuilding",
    "chemical",
    "auto",
    "content",
    "finance",
]

_SNAPSHOT_MAP = [
    ("semiconductor", semiconductor_snapshot),
    ("battery", battery_snapshot),
    ("bio", bio_snapshot),
    ("shipbuilding", shipbuilding_snapshot),
    ("chemical", chemical_snapshot),
    ("auto", auto_snapshot),
    ("content", content_snapshot),
    ("finance", finance_snapshot),
]

_SCORE_MAP = [
    ("semiconductor", semiconductor_score),
    ("battery", battery_score),
    ("bio", bio_score),
    ("shipbuilding", shipbuilding_score),
    ("chemical", chemical_score),
    ("auto", auto_score),
    ("content", content_score),
    ("finance", finance_score),
]


def fetch_all_snapshots() -> dict[str, dict]:
    """
    Fetch snapshots for all 8 sectors.
    Each sector returns {} on failure — never raises.
    """
    results: dict[str, dict] = {}
    for name, fn in _SNAPSHOT_MAP:
        try:
            results[name] = fn()
        except Exception:
            results[name] = {}
    return results


def compute_all_scores() -> dict[str, float]:
    """
    Compute scores for all 8 sectors.
    Each returns 0.0 on failure — never raises.
    """
    results: dict[str, float] = {}
    for name, fn in _SCORE_MAP:
        try:
            results[name] = fn()
        except Exception:
            results[name] = 0.0
    return results
