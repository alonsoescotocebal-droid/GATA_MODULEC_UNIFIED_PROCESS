from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_gate_module():
    repo_root = Path(__file__).resolve().parents[1]
    mod_path = repo_root / "pipeline" / "scientific_threshold_gate.py"
    spec = importlib.util.spec_from_file_location("scientific_threshold_gate", str(mod_path))
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_scientific_gate_smoke_spatial_uses_direct_signal_years_only(tmp_path):
    mod = _load_gate_module()
    smoke = tmp_path / "smoke_days_unit_2015_2024.csv"
    smoke.write_text(
        "unit_id;year;smoke_days;smoke_method\n"
        "U1;2017;3;gfas_era5_proxy_p60_unit_daily_spatial_direct_year\n"
        "U2;2017;1;gfas_era5_proxy_p60_unit_daily_spatial_direct_year\n"
        "U1;2018;0;gfas_era5_proxy_p60_unit_daily_spatial_direct_year\n"
        "U2;2018;0;gfas_era5_proxy_p60_unit_daily_spatial_direct_year\n"
        "U1;2019;0.5;gfas_era5_proxy_p60_unit_daily_spatial_interpolated_from_anchors\n"
        "U2;2019;0.5;gfas_era5_proxy_p60_unit_daily_spatial_interpolated_from_anchors\n",
        encoding="utf-8",
    )

    status, detail, counts = mod.evaluate_smoke_spatial(smoke)

    assert status == "THRESHOLD_DEFINED_AS_INTERNAL_STATISTICAL_CLASSIFICATION"
    assert 2017 in counts and counts[2017] == 2
    assert 2018 not in counts
    assert 2019 not in counts
