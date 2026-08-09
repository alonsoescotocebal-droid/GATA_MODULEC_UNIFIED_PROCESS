from __future__ import annotations

import sys
from pathlib import Path


def test_smoke_route_selector_detects_nested_recovery_root_under_datos(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import smoke_route_selector as selector  # type: ignore

    data = tmp_path / "Module C" / "Datos"
    nested_recovery = data / "Datos_RECOVERY_2015_2024_PIPELINE_GRIB"
    nested_gfas = nested_recovery / "CAM-GFAS (ADS)"
    nested_era5 = nested_recovery / "ERA5 (CDS)"
    nested_gfas.mkdir(parents=True, exist_ok=True)
    nested_era5.mkdir(parents=True, exist_ok=True)
    (nested_gfas / "dummy_pm2p5fire_20150101.grib").write_bytes(b"grib")
    (nested_gfas / "_grib_summary.csv").write_text(
        "file,minDate,message_count,pm_stride_hint\nx.grib,20150101,365,1\n",
        encoding="utf-8",
    )
    (nested_era5 / "ERA5_demo.zip").write_bytes(b"zip")
    (data / "ParquetFiles 2017.zip").write_bytes(b"zip")
    (data / "ParquetFiles 2022.zip").write_bytes(b"zip")

    sources = selector.detect_smoke_sources(data, {"paths": {"smoke_csv": str(data / "ParquetFiles 2022.zip")}})
    decision = selector.select_smoke_route(sources, decoder_available=True)

    assert sources["effective_source_is_recovery"] is True
    assert "Datos_RECOVERY_2015_2024_PIPELINE_GRIB" in sources["effective_data_root"]
    assert decision["route_selected"] == "v0_gfas_era5_advection_screening_proxy"
