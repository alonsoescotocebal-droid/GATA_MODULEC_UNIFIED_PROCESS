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
        "UniqueDates\t3653\tPASS\tok\n"
        "UniqueUnits\t26\tPASS\tok\n"
        "years_2015_2024_present\t1\tPASS\tok\n"
        "all_months_present_each_year\t1\tPASS\tok\n"
        "all_expected_dates_present\t1\tPASS\tok\n"
        "dates_per_year\t2015:365|2016:366|2017:365|2018:365|2019:365|2020:366|2021:365|2022:365|2023:365|2024:366\tPASS\tok\n"
        "months_present_by_year\t2015:ALL12|2016:ALL12|2017:ALL12|2018:ALL12|2019:ALL12|2020:ALL12|2021:ALL12|2022:ALL12|2023:ALL12|2024:ALL12\tPASS\tok\n",
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
        "unique_dates\t3653\tPASS\tok\n"
        "unique_units\t26\tPASS\tok\n"
        "years_2015_2024_present\t1\tPASS\tok\n"
        "all_months_present_each_year\t1\tPASS\tok\n"
        "all_expected_dates_present\t1\tPASS\tok\n"
        "dates_per_year\t2015:365|2016:366|2017:365|2018:365|2019:365|2020:366|2021:365|2022:365|2023:365|2024:366\tPASS\tok\n"
        "months_present_by_year\t2015:ALL12|2016:ALL12|2017:ALL12|2018:ALL12|2019:ALL12|2020:ALL12|2021:ALL12|2022:ALL12|2023:ALL12|2024:ALL12\tPASS\tok\n",
    )
    smoke_rows = ["year\tunique_values\tmethod\tspatial_homogeneous_flag"]
    smoke_rows.extend(
        f"{year}\t3\tgfas_pm2p5fire_gdal_daily_spatial_direct_year\t0" for year in range(2015, 2025)
    )
    _write(qa / "smoke_route_audit.tsv", "\n".join(smoke_rows) + "\n")

    status, detail = mod.evaluate_direct_decoder_contract(output_root)

    assert status == "THRESHOLD_DEFINED_AS_INDEXED_METHOD"
    assert "all_expected_dates_present=1" in detail

def test_direct_decoder_contract_prefers_tab_for_tsv_with_semicolon_heavy_detail(tmp_path):
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
        "unique_years\t10\tPASS\tcoverage=2015;2016;2017;2018;2019;2020;2021;2022;2023;2024\n"
        "unique_dates\t3653\tPASS\trows=94978; units=26; days=3653; source=recovery; method=direct; check=ok\n"
        "unique_units\t26\tPASS\tPT11;PT15;PT16;PT17;PT18;PT19;PT20;PT30\n"
        "years_2015_2024_present\t1\tPASS\tall years present; no gaps; no truncation\n"
        "all_months_present_each_year\t1\tPASS\tall months present; no Jan-Apr bias; no collapse\n"
        "all_expected_dates_present\t1\tPASS\tcalendar complete; leap years preserved; no cap applied\n"
        "dates_per_year\t2015:365|2016:366|2017:365|2018:365|2019:365|2020:366|2021:365|2022:365|2023:365|2024:366\tPASS\tverified; persisted; audited\n"
        "months_present_by_year\t2015:ALL12|2016:ALL12|2017:ALL12|2018:ALL12|2019:ALL12|2020:ALL12|2021:ALL12|2022:ALL12|2023:ALL12|2024:ALL12\tPASS\tverified; persisted; audited\n",
    )
    smoke_rows = ["year\tunique_values\tmethod\tspatial_homogeneous_flag"]
    smoke_rows.extend(
        f"{year}\t3\tgfas_pm2p5fire_gdal_daily_spatial_direct_year\t0" for year in range(2015, 2025)
    )
    _write(qa / "smoke_route_audit.tsv", "\n".join(smoke_rows) + "\n")

    status, detail = mod.evaluate_direct_decoder_contract(output_root)

    assert status == "THRESHOLD_DEFINED_AS_INDEXED_METHOD"
    assert "unique_years=10" in detail
