from __future__ import annotations

import json
import sys
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import scientific_threshold_gate as mod  # type: ignore

    return mod


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_direct_decoder_contract_allows_recovery_cam_gfas_ads_path(tmp_path):
    mod = _load_module()
    output_root = tmp_path / "runtime"
    qa = output_root / "qa"

    _write(
        qa / "inputs_resolved.json",
        json.dumps(
            {
                "paths": {
                    "smoke_effective_data_root": r"D:\X\Datos_RECOVERY_2015_2024_PIPELINE_GRIB",
                    "smoke_effective_source_path": r"D:\X\Datos_RECOVERY_2015_2024_PIPELINE_GRIB\CAM-GFAS (ADS)",
                },
                "meta": {
                    "smoke_route_selected": "v0_gfas_era5_real",
                    "smoke_route_detected_sources": {"effective_source_is_recovery": True},
                },
            }
        ),
    )
    _write(
        qa / "gfas_era5_decoder_daily_spatial_audit.tsv",
        "metric\tvalue\tstatus\tdetail\n"
        "UniqueYears\t10\tPASS\tok\n"
        "UniqueDates\t930\tPASS\tok\n",
    )
    smoke_rows = ["year\tunique_values\tmethod\tspatial_homogeneous_flag"]
    smoke_rows.extend(
        f"{year}\t3\tgfas_pm2p5fire_gdal_daily_spatial_direct_year\t0" for year in range(2015, 2025)
    )
    _write(qa / "smoke_route_audit.tsv", "\n".join(smoke_rows) + "\n")

    status, detail = mod.evaluate_direct_decoder_contract(output_root)

    assert status == "THRESHOLD_DEFINED_AS_INDEXED_METHOD"
    assert "unique_years=10" in detail


def test_direct_decoder_contract_accepts_lowercase_daily_spatial_metrics(tmp_path):
    mod = _load_module()
    output_root = tmp_path / "runtime"
    qa = output_root / "qa"

    _write(
        qa / "inputs_resolved.json",
        json.dumps(
            {
                "paths": {
                    "smoke_effective_data_root": r"D:\X\Datos_RECOVERY_2015_2024_PIPELINE_GRIB",
                    "smoke_effective_source_path": r"D:\X\Datos_RECOVERY_2015_2024_PIPELINE_GRIB\CAM-GFAS (ADS)",
                },
                "meta": {
                    "smoke_route_selected": "v0_gfas_era5_real",
                    "smoke_route_detected_sources": {"effective_source_is_recovery": True},
                },
            }
        ),
    )
    _write(
        qa / "gfas_era5_decoder_daily_spatial_audit.tsv",
        "metric\tvalue\tstatus\tdetail\n"
        "unique_years\t10\tPASS\tok\n"
        "unique_dates\t930\tPASS\tok\n",
    )
    smoke_rows = ["year\tunique_values\tmethod\tspatial_homogeneous_flag"]
    smoke_rows.extend(
        f"{year}\t3\tgfas_pm2p5fire_gdal_daily_spatial_direct_year\t0" for year in range(2015, 2025)
    )
    _write(qa / "smoke_route_audit.tsv", "\n".join(smoke_rows) + "\n")

    status, detail = mod.evaluate_direct_decoder_contract(output_root)

    assert status == "THRESHOLD_DEFINED_AS_INDEXED_METHOD"
    assert "unique_dates=930" in detail
