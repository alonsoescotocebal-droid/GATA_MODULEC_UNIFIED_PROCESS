from __future__ import annotations

import sys
from pathlib import Path


def test_apply_route_meta_writes_gfas_era5_trace(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import smoke_route_selector as selector  # type: ignore

    data = tmp_path / "Module C" / "Datos"
    recovery = tmp_path / "Module C" / "Datos_RECOVERY_2015_2024_PIPELINE_GRIB"
    data.mkdir(parents=True, exist_ok=True)
    recovery.mkdir(parents=True, exist_ok=True)
    gfas_dir = recovery
    (gfas_dir / "dummy.grib").write_bytes(b"grib")
    (gfas_dir / "_grib_summary.csv").write_text("file,minDate,message_count,pm_stride_hint\nx.grib,20150101,365,1\n", encoding="utf-8")
    era5_zip = recovery / "ERA5_demo.zip"
    era5_zip.write_bytes(b"zip")
    (data / "ParquetFiles 2022.zip").write_bytes(b"zip")

    inputs = {"paths": {"smoke_csv": str(data / "ParquetFiles 2022.zip")}, "meta": {}}
    sources = selector.detect_smoke_sources(data, inputs)
    decision = selector.select_smoke_route(sources, decoder_available=False)
    enriched = selector.apply_route_meta(inputs, sources, decision)

    assert enriched["paths"]["smoke_gfas_dir"] == str(gfas_dir)
    assert enriched["paths"]["smoke_era5_zip"] == str(era5_zip)
    assert enriched["paths"]["smoke_effective_data_root"] == str(recovery)
    assert enriched["paths"]["smoke_effective_source_path"] == str(gfas_dir)
    assert enriched["meta"]["smoke_route_selected"] == "BLOCKED_DECODER_REQUIRED"
    assert enriched["meta"]["smoke_route_decision"] == "BLOCKED_DECODER_REQUIRED"
    assert enriched["meta"]["smoke_route_detected_sources"]["effective_source_is_recovery"] is True
