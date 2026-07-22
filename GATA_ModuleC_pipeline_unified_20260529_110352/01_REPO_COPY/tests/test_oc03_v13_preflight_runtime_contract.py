from __future__ import annotations

import sys
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import moduleC_pipeline_v2 as mod  # type: ignore

    return mod


def test_refresh_preflight_report_writes_runtime_artifact_and_canon_meta(tmp_path):
    mod = _load_module()

    runtime = tmp_path / "runtime"
    gata_root = tmp_path / "gata_root"
    modulec_datos = tmp_path / "modulec_datos"
    inc_new = tmp_path / "inc_new"
    for path in (gata_root, modulec_datos, inc_new):
        path.mkdir(parents=True, exist_ok=True)

    smoke_zip = modulec_datos / "ParquetFiles 2022.zip"
    smoke_zip.write_text("placeholder", encoding="utf-8")
    nuts3 = tmp_path / "inputs" / "nuts3.gpkg"
    municipios = tmp_path / "inputs" / "municipios.gpkg"
    wrb = tmp_path / "inputs" / "wrb.tif"
    fire = tmp_path / "inputs" / "fire_2015.gpkg"
    for path in (nuts3, municipios, wrb, fire):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("placeholder", encoding="utf-8")
    ghsl_dir = tmp_path / "inputs" / "ghsl"
    ghsl_dir.mkdir(parents=True, exist_ok=True)
    ghsl = {}
    for year in ("2015", "2020", "2025", "2030"):
        path = ghsl_dir / f"ghsl_{year}.tif"
        path.write_text("placeholder", encoding="utf-8")
        ghsl[year] = str(path)

    inputs = {
        "paths": {
            "nuts3": str(nuts3),
            "municipios_caop": str(municipios),
            "smoke_csv": str(smoke_zip),
            "ghsl_pop": ghsl,
            "fire_gpkgs_tm06": [str(fire)],
            "wrb_mostprobable_tm06": str(wrb),
            "smoke_effective_data_root": r"D:\X\Datos_RECOVERY_2015_2024_PIPELINE_GRIB",
            "smoke_effective_source_path": r"D:\X\Datos_RECOVERY_2015_2024_PIPELINE_GRIB\CAM-GFAS (ADS)",
        }
    }
    inputs = mod.hydrate_inputs_contract_meta(inputs)
    report = mod.Report(runtime / "qa" / "report_auditoria_v2.txt")

    out_path = mod.refresh_preflight_report(
        gata_root=gata_root,
        modulec_datos=modulec_datos,
        inc_new=inc_new,
        output_root=runtime,
        inputs=inputs,
        route_decision={
            "route_selected": "v0_gfas_era5_real",
            "smoke_route_decision": "THRESHOLD_DEFINED_AS_INDEXED_METHOD",
        },
        report=report,
        qgis_ready=False,
    )

    text = out_path.read_text(encoding="utf-8")
    assert out_path.exists()
    assert "smoke route preflight selected=v0_gfas_era5_real" in text
    assert "smoke effective data root: D:\\X\\Datos_RECOVERY_2015_2024_PIPELINE_GRIB" in text
    assert "END HOLD preflight (missing inputs)" in text
