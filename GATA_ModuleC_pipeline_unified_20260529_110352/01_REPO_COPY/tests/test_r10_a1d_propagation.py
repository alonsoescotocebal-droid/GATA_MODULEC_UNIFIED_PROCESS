from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_modulec():
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    path = repo_root / "pipeline" / "moduleC_pipeline_v2.py"
    spec = importlib.util.spec_from_file_location("modulec_r10_a1d", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_step7():
    repo_root = Path(__file__).resolve().parents[1]
    step7_dir = repo_root / "pipeline" / "RUN_QGIS" / "STEP7_MATRIZ_CAUSAL"
    sys.path.insert(0, str(step7_dir))
    path = step7_dir / "step7_matriz_causal.py"
    spec = importlib.util.spec_from_file_location("step7_r10_a1d", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _canonical_scenario(path: Path) -> Path:
    return _write(
        path,
        "unit_id;year;scenario;population_smoke_day_burden_proxy;"
        "delta_population_smoke_day_burden_proxy_vs_S0;"
        "delta_smoke_day_burden_vs_S0\n"
        "U1;2026;S0;100;0;0\n"
        "U1;2026;S1;80;-20;-20\n"
        "U1;2027;S0;120;0;0\n"
        "U1;2027;S1;96;-24;-24\n",
    )


def test_scenario_audit_accepts_canonical_delta_without_legacy_aliases(tmp_path):
    step7 = _load_step7()
    unit = _canonical_scenario(tmp_path / "unit.csv")
    muni = _canonical_scenario(tmp_path / "muni.csv")

    step7.write_scenario_audit(tmp_path, unit, muni)
    rows = {row["metric"]: row for row in step7.read_csv_rows(tmp_path / "qa" / "scenario_audit.tsv")[1]}

    assert rows["scenario_delta_nonempty"]["status"] == "PASS"
    assert int(rows["scenario_delta_nonempty"]["value"]) > 0


def test_scenario_aggregate_audit_uses_canonical_burden_and_delta(tmp_path):
    step7 = _load_step7()
    hist_detail = _write(tmp_path / "hist.csv", "unit_id;population_smoke_day_burden_proxy\nU1;100\n")
    hist_mean = _write(tmp_path / "hist_mean.csv", "unit_id;population_smoke_day_burden_proxy_mean_2015_2024\nU1;100\n")
    scenario_detail = _canonical_scenario(tmp_path / "scenario.csv")
    scenario_mean = _write(
        tmp_path / "scenario_mean.csv",
        "unit_id;population_smoke_day_burden_proxy_S0_mean_2026_2030;"
        "population_smoke_day_burden_proxy_S1_mean_2026_2030;"
        "delta_population_smoke_day_burden_proxy_S1_minus_S0\n"
        "U1;110;88;-22\n",
    )

    step7.write_aggregate_consistency_audits(
        tmp_path,
        hist_detail,
        hist_mean,
        hist_detail,
        hist_mean,
        scenario_detail,
        scenario_mean,
        scenario_detail,
        scenario_mean,
    )
    rows = step7.read_csv_rows(tmp_path / "qa" / "scenario_aggregate_consistency_audit.tsv")[1]
    scenario_rows = [row for row in rows if row["unit_id"] == "U1"]

    assert scenario_rows
    assert all(row["status"] == "PASS" for row in scenario_rows)
    assert all(float(row["observed_delta"]) == float(row["expected_delta"]) for row in scenario_rows)


def test_oc03_decoder_audit_uses_canonical_smoke_and_burden_outputs(tmp_path):
    mod = _load_modulec()
    qa = tmp_path / "qa"
    tables = tmp_path / "tables"
    _write(qa / "inputs_resolved.json", json.dumps({"meta": {"smoke_route_selected": "v0_gfas_era5_real"}}))
    _write(
        qa / "gfas_era5_decoder_backend_audit.tsv",
        "metric\tstatus\n"
        "decoder_available\tPASS\nbackend_gfas\tPASS\nbackend_era5\tPASS\n",
    )
    _write(qa / "smoke_route_audit.tsv", "year\tspatial_homogeneous_flag\n2015\t0\n")
    _write(
        qa / "gfas_pm2p5fire_portugal_daily_summary.csv",
        "date;year\n" + "\n".join(f"2015-01-{day:02d};2015" for day in range(1, 12)) + "\n",
    )
    _write(
        tables / "smoke_days_unit_2015_2024.csv",
        "unit_id;year;smoke_days\nU1;2015;2\nU2;2015;4\n",
    )
    _write(
        tables / "smoke_days_municipio_2015_2024.csv",
        "unit_id;year;smoke_days\nM1;2015;1\nM2;2015;3\n",
    )
    _write(
        tables / "IECH_unit_2015_2024_mean.csv",
        "unit_id;population_smoke_day_burden_proxy_mean_2015_2024\nU1;200\nU2;400\n",
    )
    _write(
        tables / "IECH_municipio_2015_2024_mean.csv",
        "unit_id;population_smoke_day_burden_proxy_mean_2015_2024\nM1;100\nM2;300\n",
    )

    mod.write_oc03_v11_decoder_contract_validation(tmp_path)
    rows = {row["metric"]: row for row in mod.read_csv_rows(qa / "oc03_v11_decoder_contract_validation.tsv")[1]}

    assert rows["SmokeDayUnitUniqueCount"]["status"] == "PASS"
    assert rows["PopulationSmokeDayBurdenUnitUniqueMeanCount"]["status"] == "PASS"
    assert "IECHUnitUniqueMeanCount" not in rows
    assert "IECHMunicipioUniqueMeanCount" not in rows
