from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_step7_module():
    repo_root = Path(__file__).resolve().parents[1]
    pipeline_root = repo_root / "pipeline"
    if str(pipeline_root) not in sys.path:
        sys.path.insert(0, str(pipeline_root))
    mod_path = repo_root / "pipeline" / "RUN_QGIS" / "STEP7_MATRIZ_CAUSAL" / "step7_matriz_causal.py"
    spec = importlib.util.spec_from_file_location("step7_matriz_causal", str(mod_path))
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_step7_smoke_homogeneous_helper_blocks(tmp_path):
    mod = _load_step7_module()
    smoke = tmp_path / "smoke_days_unit_2015_2024.csv"
    smoke.write_text(
        "unit_id;year;smoke_days\n"
        "U1;2015;10\n"
        "U2;2015;10\n",
        encoding="utf-8",
    )
    assert mod._smoke_spatial_homogeneous(smoke) is True


def test_step7_smoke_homogeneous_helper_ignores_zero_signal_direct_year(tmp_path):
    mod = _load_step7_module()
    smoke = tmp_path / "smoke_days_unit_2015_2024.csv"
    smoke.write_text(
        "unit_id;year;smoke_days;smoke_method\n"
        "U1;2017;3;gfas_era5_proxy_p60_unit_daily_spatial_direct_year\n"
        "U2;2017;1;gfas_era5_proxy_p60_unit_daily_spatial_direct_year\n"
        "U1;2018;0;gfas_era5_proxy_p60_unit_daily_spatial_direct_year\n"
        "U2;2018;0;gfas_era5_proxy_p60_unit_daily_spatial_direct_year\n",
        encoding="utf-8",
    )
    assert mod._smoke_spatial_homogeneous(smoke) is False


def test_step7_iech_cancellation_helper_blocks(tmp_path):
    mod = _load_step7_module()
    iech = tmp_path / "IECH_unit_2015_2024.csv"
    iech.write_text(
        "unit_id;year;smoke_days;population_total;population_smoke_day_burden_proxy\n"
        "U1;2015;10;100;1000\n"
        "U2;2015;20;200;4000\n",
        encoding="utf-8",
    )
    assert mod._iech_population_cancellation(iech) is True


def test_step7_maps_municipio_smoke_from_parent_nuts3(tmp_path):
    mod = _load_step7_module()
    smoke_unit = tmp_path / "smoke_days_unit_2015_2024.csv"
    smoke_rows = ["unit_id;year;smoke_days;smoke_score_mean;smoke_score_p80;smoke_method;smoke_missing_flag"]
    for year in range(2015, 2025):
        smoke_rows.append(f"PT11;{year};12;1.2;2.0;daily_spatial;0")
        smoke_rows.append(f"PT15;{year};3;0.3;0.4;daily_spatial;0")
    smoke_unit.write_text(
        "\n".join(smoke_rows) + "\n",
        encoding="utf-8",
    )
    muni_map = tmp_path / "municipio_unit_map.csv"
    muni_map.write_text(
        "municipio_id;nuts3_id;mapping_ok\n"
        "MUN_A;PT11;1\n"
        "MUN_B;PT15;1\n",
        encoding="utf-8",
    )
    smoke_muni = tmp_path / "smoke_days_municipio_2015_2024.csv"
    mod.write_smoke_table_from_nuts_map(smoke_unit, muni_map, smoke_muni)

    rows = mod.read_csv_rows(smoke_muni)[1]
    by_unit = {r["unit_id"]: r for r in rows if r.get("year") == "2017"}
    assert by_unit["MUN_A"]["smoke_days"] == "12"
    assert by_unit["MUN_B"]["smoke_days"] == "3"

def test_step7_area_principal_expression_covers_real_utf8_variant():
    mod = _load_step7_module()
    expr = mod._build_area_principal_expression("tipo_area_administrativa")
    assert "\"tipo_area_administrativa\" = 'Área Principal'" in expr
    assert "\"tipo_area_administrativa\" = 'Area Principal'" in expr
    assert expr.count(" OR ") == 2
