from __future__ import annotations

import csv
import sys
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import moduleC_pipeline_v2 as mod  # type: ignore

    return mod


def _load_validator():
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import validate_modulec_objectives_canon as mod  # type: ignore

    return mod


def test_direct_recovery_trace_audit_uses_effective_source_and_not_modulea_hold(tmp_path):
    mod = _load_module()
    qa_dir = tmp_path / "qa"
    inputs = {
        "paths": {
            "smoke_csv": r"D:\legacy\ParquetFiles 2022.zip",
            "smoke_effective_source_path": r"D:\X\Datos_RECOVERY_2015_2024_PIPELINE_GRIB\CAM-GFAS (ADS)",
            "smoke_effective_data_root": r"D:\X\Datos_RECOVERY_2015_2024_PIPELINE_GRIB",
        },
        "meta": {
            "smoke_route_selected": "v0_gfas_era5_real",
        },
    }
    sources = {
        "smoke_csv_input": r"D:\legacy\ParquetFiles 2022.zip",
        "modulea_validated": False,
        "gfas_exists": True,
        "era5_exists": True,
        "effective_source_is_recovery": True,
        "effective_smoke_source_path": r"D:\X\Datos_RECOVERY_2015_2024_PIPELINE_GRIB\CAM-GFAS (ADS)",
        "effective_data_root": r"D:\X\Datos_RECOVERY_2015_2024_PIPELINE_GRIB",
        "forbidden_primary_source": False,
    }
    route_decision = {
        "route_selected": "v0_gfas_era5_real",
        "smoke_route_decision": "THRESHOLD_DEFINED_AS_INDEXED_METHOD",
    }

    mod.write_smoke_route_source_trace_audit(qa_dir, inputs, sources, route_decision)

    with (qa_dir / "smoke_route_source_trace_audit.tsv").open(encoding="utf-8", newline="") as fh:
        rows = {row["check_id"]: row for row in csv.DictReader(fh, delimiter="\t")}

    assert rows["TRACE-001"]["status"] == "PASS"
    assert rows["TRACE-001"]["value"] == sources["effective_smoke_source_path"]
    assert rows["TRACE-001"]["evidence"] == "inputs_resolved.paths.smoke_effective_source_path"
    assert rows["TRACE-002"]["status"] == "PASS"
    assert rows["TRACE-002"]["value"] == "DIRECT_RECOVERY_ROUTE_NOT_APPLICABLE"
    assert rows["TRACE-009"]["status"] == "PASS"
    assert rows["TRACE-009"]["value"] == sources["effective_data_root"]
    assert rows["TRACE-010"]["status"] == "PASS"


def test_v0_audit_accepts_declared_non_health_limitation_when_probe_is_clean(tmp_path):
    mod = _load_validator()
    output_root = tmp_path / "runtime"
    qa_dir = output_root / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    (qa_dir / "smoke_route_v0_audit.tsv").write_text(
        "metric\tvalue\tstatus\tdetail\n"
        "backend_gfas\tGDAL\tPASS\tGFAS decoded through GDAL-only message extraction path.\n"
        "backend_era5\tGDAL\tPASS\tERA5 10U/10V validated through GDAL.\n"
        "health_exposure_claim\tNON_HEALTH_LIMITATION_DECLARED\tPASS\tNo official pollutant threshold validation in this v0 route.\n"
        "unexplained_warnings_count\t0\tPASS\t\n",
        encoding="utf-8",
    )

    ok, reason = mod._v10b_v0_audit_not_blocked(output_root)

    assert ok is True
    assert "no blocking findings" in reason.lower()


def test_post_smoke_completion_runs_step9_build_before_post_objectives_and_supports_resume_flag():
    repo_root = Path(__file__).resolve().parents[1]
    pipeline = repo_root / "pipeline" / "moduleC_pipeline_v2.py"
    text = pipeline.read_text(encoding="utf-8", errors="replace")

    assert 'ap.add_argument("--resume-post-smoke", action="store_true")' in text
    assert "refresh_preflight_report(" in text
    assert "run_path_scope_guard(" in text

    start = text.index("def complete_post_smoke_runtime(")
    end = text.index("def main()")
    section = text[start:end]

    assert section.index("build_manifest_and_zip(outputs, deliver_dir, report)") < section.index(
        'run_objectives_gate(output_root, report, mode="post")'
    )
    assert section.index("run_global_audit_status_scan(output_root, report)") < section.index(
        "build_manifest_and_zip(outputs, deliver_dir, report)",
        section.index('run_objectives_gate(output_root, report, mode="post")')
    )
