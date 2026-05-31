from __future__ import annotations

import sys
from pathlib import Path


def test_apply_route_meta_writes_gfas_era5_trace(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import smoke_route_selector as selector  # type: ignore

    data = tmp_path / "Datos"
    data.mkdir(parents=True, exist_ok=True)
    gfas_dir = data / "CAM-GFAS (ADS)"
    gfas_dir.mkdir(parents=True, exist_ok=True)
    (gfas_dir / "dummy.grib").write_bytes(b"grib")
    era5_zip = data / "ERA5_demo.zip"
    era5_zip.write_bytes(b"zip")
    (data / "ParquetFiles 2022.zip").write_bytes(b"zip")

    inputs = {"paths": {"smoke_csv": str(data / "ParquetFiles 2022.zip")}, "meta": {}}
    sources = selector.detect_smoke_sources(data, inputs)
    decision = selector.select_smoke_route(sources, decoder_available=False)
    enriched = selector.apply_route_meta(inputs, sources, decision)

    assert enriched["paths"]["smoke_gfas_dir"] == str(gfas_dir)
    assert enriched["paths"]["smoke_era5_zip"] == str(era5_zip)
    assert enriched["meta"]["smoke_route_selected"] == "BLOCKED_DECODER_REQUIRED"
    assert enriched["meta"]["smoke_route_decision"] == "BLOCKED_DECODER_REQUIRED"
