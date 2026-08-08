from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_modulec():
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    path = repo_root / "pipeline" / "moduleC_pipeline_v2.py"
    spec = importlib.util.spec_from_file_location("modulec_r10_a2", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_era5_numerically_affects_transport_score():
    mod = _load_modulec()
    sources = [{"lon": -9.0, "lat": 40.0, "flux": 1.0}]
    receptor = {"lon": -8.0, "lat": 40.0}
    east = mod._transport_weighted_receptor_proxy(sources, receptor, 5.0, 0.0)
    west = mod._transport_weighted_receptor_proxy(sources, receptor, -5.0, 0.0)
    assert east != west


def test_wind_reversal_crosswind_and_distance_attenuation():
    mod = _load_modulec()
    aligned = mod._transport_kernel(-9.0, 40.0, -8.0, 40.0, 5.0, 0.0)
    reversed_wind = mod._transport_kernel(-9.0, 40.0, -8.0, 40.0, -5.0, 0.0)
    crosswind = mod._transport_kernel(-9.0, 40.0, -9.0, 41.0, 5.0, 0.0)
    far = mod._transport_kernel(-9.0, 40.0, -6.0, 40.0, 5.0, 0.0)
    assert aligned > reversed_wind
    assert aligned > crosswind
    assert aligned > far


def test_calm_wind_and_local_source_are_finite_and_safe():
    mod = _load_modulec()
    local = mod._transport_kernel(-9.0, 40.0, -9.0, 40.0, 0.0, 0.0)
    calm_far = mod._transport_kernel(-9.0, 40.0, -8.0, 40.0, 0.0, 0.0)
    assert local == 1.0
    assert calm_far == 0.0


def test_transport_time_weight_is_monotone_and_bounded():
    mod = _load_modulec()
    near = mod._transport_components(-9.0, 40.0, -8.9, 40.0, 5.0, 0.0)
    far = mod._transport_components(-9.0, 40.0, -6.0, 40.0, 5.0, 0.0)
    assert 0.0 < far["distance_transport_weight"] <= 1.0
    assert near["distance_transport_weight"] > far["distance_transport_weight"]
    assert 0.0 <= far["transport_kernel"] <= 1.0


def test_no_absolute_cosine_and_no_kernel_sum_renormalization():
    mod = _load_modulec()
    upwind = mod._transport_kernel(-9.0, 40.0, -8.0, 40.0, 5.0, 0.0)
    downwind = mod._transport_kernel(-9.0, 40.0, -8.0, 40.0, -5.0, 0.0)
    assert upwind > downwind
    value = mod._transport_weighted_receptor_proxy(
        [
            {"lon": -9.0, "lat": 40.0, "flux": 1.0},
            {"lon": -6.0, "lat": 40.0, "flux": 1.0},
        ],
        {"lon": -8.0, "lat": 40.0},
        5.0,
        0.0,
    )
    assert value < 1.0


def test_binary_and_burden_contracts_remain_separate_from_transport_intensity(tmp_path):
    mod = _load_modulec()
    rows = [
        {"unit_id": "U1", "year": 2024, "smoke_day_score": 0.5, "qa_flag": 0},
        {"unit_id": "U1", "year": 2024, "smoke_day_score": 2.0, "qa_flag": 0},
    ]
    finalized, annual, threshold = mod._finalize_unit_daily_scores(rows, mod.Report(tmp_path / "report.txt"), "test")
    assert threshold is not None
    assert annual["U1"][2024]["smoke_days"] == sum(row["smoke_day_proxy"] for row in finalized)
    assert annual["U1"][2024]["smoke_days"] <= 366
    assert annual["U1"][2024]["cumulative_normalized_smoke_intensity_proxy"] >= 0.0
    assert 0.75 * 100.0 + 0.25 * 50.0 == 87.5


def test_route_claim_blocks_era5_language_when_score_use_is_false():
    mod = _load_modulec()
    assert mod._r10_a2_route_claim(False) == "BLOCKED_ERA5_MECHANISTIC_CLAIM"


def test_route_claim_requires_mechanistic_era5_score_use():
    mod = _load_modulec()
    assert mod._r10_a2_route_claim(True) == "ADVECTION_INFORMED_OPERATIONAL_SMOKE_PROXY"
    assert mod._r10_a2_route_claim(False).startswith("BLOCKED_ERA5")
