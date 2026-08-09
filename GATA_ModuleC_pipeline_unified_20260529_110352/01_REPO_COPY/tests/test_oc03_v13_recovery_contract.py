from __future__ import annotations

import json
import sys
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import validate_modulec_objectives_canon as mod  # type: ignore

    return mod


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_oc03_v13_direct_contract_rejects_v9d_signature(tmp_path):
    mod = _load_module()
    output_root = tmp_path / "runtime"
    qa = output_root / "qa"
    tables = output_root / "tables"

    _write(
        qa / "inputs_resolved.json",
        json.dumps(
            {
                "paths": {
                    "smoke_effective_data_root": r"D:\X\Datos_RECOVERY_2015_2024_PIPELINE_GRIB",
                    "smoke_effective_source_path": r"D:\X\Datos_RECOVERY_2015_2024_PIPELINE_GRIB\CAM-GFAS-RECOVERY",
                },
                "meta": {
                    "smoke_route_selected": "v0_gfas_era5_advection_screening_proxy",
                    "smoke_route_detected_sources": {"effective_source_is_recovery": True},
                },
            }
        ),
    )
    _write(
        qa / "smoke_route_audit.tsv",
        "year\tunique_values\tsmoke_method\tspatial_homogeneous_flag\n"
        + "\n".join(f"{year}\t1\tgfas_pm2p5fire_gdal_daily_spatial_direct_year\t1" for year in range(2015, 2025))
        + "\n",
    )
    _write(
        qa / "gfas_era5_decoder_daily_spatial_audit.tsv",
        "metric\tvalue\tstatus\tdetail\n"
        "UniqueYears\t1\tHOLD\ttoo few\n"
        "UniqueDates\t93\tHOLD\ttoo few\n",
    )
    _write(
        tables / "IECH_unit_2015_2024_mean.csv",
        "unit_id;IECH_mean_2015_2024\nA;1\nB;1\nC;1\nD;1\n",
    )
    _write(
        tables / "IECH_municipio_2015_2024_mean.csv",
        "municipio_id;IECH_mean_2015_2024\nA;1\nB;1\nC;1\nD;1\n",
    )
    _write(
        tables / "smoke_days_unit_2015_2024.csv",
        "unit_id;year;smoke_days\n" + "\n".join(f"U{i};2015;1" for i in range(4)) + "\n",
    )

    ok, reason = mod._check_oc03_v13_direct_contract(output_root, json.loads((qa / "inputs_resolved.json").read_text(encoding="utf-8")))

    assert ok is False
    assert "unique_years=1" in reason.lower() or "v9d" in reason.lower() or "homogeneous" in reason.lower()


def test_oc03_v13_direct_contract_accepts_recovery_metrics(tmp_path):
    mod = _load_module()
    output_root = tmp_path / "runtime"
    qa = output_root / "qa"
    tables = output_root / "tables"

    _write(
        qa / "inputs_resolved.json",
        json.dumps(
            {
                "paths": {
                    "smoke_effective_data_root": r"D:\X\Datos_RECOVERY_2015_2024_PIPELINE_GRIB",
                    "smoke_effective_source_path": r"D:\X\Datos_RECOVERY_2015_2024_PIPELINE_GRIB\CAM-GFAS (ADS)",
                },
                "meta": {
                    "smoke_route_selected": "v0_gfas_era5_advection_screening_proxy",
                    "smoke_route_detected_sources": {"effective_source_is_recovery": True},
                },
            }
        ),
    )
    smoke_rows = ["year\tunique_values\tmethod\tspatial_homogeneous_flag"]
    smoke_rows.extend(
        f"{year}\t{year - 2010}\tgfas_pm2p5fire_gdal_daily_spatial_direct_year\t0" for year in range(2015, 2025)
    )
    _write(qa / "smoke_route_audit.tsv", "\n".join(smoke_rows) + "\n")
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
    unit_rows = ["unit_id;IECH_mean_2015_2024"]
    unit_rows.extend(f"U{i};{i}" for i in range(1, 25))
    _write(tables / "IECH_unit_2015_2024_mean.csv", "\n".join(unit_rows) + "\n")
    muni_rows = ["municipio_id;IECH_mean_2015_2024"]
    muni_rows.extend(f"M{i};{i}" for i in range(1, 280))
    _write(tables / "IECH_municipio_2015_2024_mean.csv", "\n".join(muni_rows) + "\n")
    smoke_unit_rows = ["unit_id;year;smoke_days"]
    smoke_unit_rows.extend(f"U{i};2015;{i}" for i in range(1, 10))
    _write(tables / "smoke_days_unit_2015_2024.csv", "\n".join(smoke_unit_rows) + "\n")

    ok, reason = mod._check_oc03_v13_direct_contract(output_root, json.loads((qa / "inputs_resolved.json").read_text(encoding="utf-8")))

    assert ok is True
    assert "unique_years=10" in reason

def test_oc03_v13_direct_contract_prefers_tab_tsv_when_detail_contains_many_semicolons(tmp_path):
    mod = _load_module()
    output_root = tmp_path / "runtime"
    qa = output_root / "qa"
    tables = output_root / "tables"

    _write(
        qa / "inputs_resolved.json",
        json.dumps(
            {
                "paths": {
                    "smoke_effective_data_root": r"D:\X\Datos_RECOVERY_2015_2024_PIPELINE_GRIB",
                    "smoke_effective_source_path": r"D:\X\Datos_RECOVERY_2015_2024_PIPELINE_GRIB\CAM-GFAS (ADS)",
                },
                "meta": {
                    "smoke_route_selected": "v0_gfas_era5_advection_screening_proxy",
                    "smoke_route_detected_sources": {"effective_source_is_recovery": True},
                },
            }
        ),
    )
    smoke_rows = ["year\tunique_values\tmethod\tspatial_homogeneous_flag"]
    smoke_rows.extend(
        f"{year}\t{year - 2010}\tgfas_pm2p5fire_gdal_daily_spatial_direct_year\t0" for year in range(2015, 2025)
    )
    _write(qa / "smoke_route_audit.tsv", "\n".join(smoke_rows) + "\n")
    _write(
        qa / "gfas_era5_decoder_daily_spatial_audit.tsv",
        "metric\tvalue\tstatus\tdetail\n"
        "unique_years\t10\tPASS\tcoverage=2015;2016;2017;2018;2019;2020;2021;2022;2023;2024\n"
        "unique_dates\t3653\tPASS\trows=94978; units=26; days=3653; contract=full; source=recovery; method=direct\n"
        "unique_units\t26\tPASS\tPT11;PT15;PT16;PT17;PT18;PT19;PT20;PT30\n"
        "years_2015_2024_present\t1\tPASS\tall years present; no gaps; no truncation\n"
        "all_months_present_each_year\t1\tPASS\tall months present; no Jan-Apr bias; no single-season collapse\n"
        "all_expected_dates_present\t1\tPASS\tcalendar complete; leap years preserved; no cap applied\n"
        "dates_per_year\t2015:365|2016:366|2017:365|2018:365|2019:365|2020:366|2021:365|2022:365|2023:365|2024:366\tPASS\tverified; persisted; audited\n"
        "months_present_by_year\t2015:ALL12|2016:ALL12|2017:ALL12|2018:ALL12|2019:ALL12|2020:ALL12|2021:ALL12|2022:ALL12|2023:ALL12|2024:ALL12\tPASS\tverified; persisted; audited\n",
    )
    unit_rows = ["unit_id;IECH_mean_2015_2024"]
    unit_rows.extend(f"U{i};{i}" for i in range(1, 25))
    _write(tables / "IECH_unit_2015_2024_mean.csv", "\n".join(unit_rows) + "\n")
    muni_rows = ["municipio_id;IECH_mean_2015_2024"]
    muni_rows.extend(f"M{i};{i}" for i in range(1, 280))
    _write(tables / "IECH_municipio_2015_2024_mean.csv", "\n".join(muni_rows) + "\n")
    smoke_unit_rows = ["unit_id;year;smoke_days"]
    smoke_unit_rows.extend(f"U{i};2015;{i}" for i in range(1, 10))
    _write(tables / "smoke_days_unit_2015_2024.csv", "\n".join(smoke_unit_rows) + "\n")

    ok, reason = mod._check_oc03_v13_direct_contract(output_root, json.loads((qa / "inputs_resolved.json").read_text(encoding="utf-8")))

    assert ok is True
    assert "unique_years=10" in reason
