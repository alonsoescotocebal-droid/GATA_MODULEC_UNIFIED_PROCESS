from __future__ import annotations

import sys
from pathlib import Path


def test_smoke_route_selector_prefers_gfas_era5_over_parquet_final(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import smoke_route_selector as selector  # type: ignore

    data = tmp_path / "Datos"
    data.mkdir(parents=True, exist_ok=True)
    (data / "CAM-GFAS (ADS)").mkdir(parents=True, exist_ok=True)
    (data / "CAM-GFAS (ADS)" / "dummy.grib").write_bytes(b"grib")
    (data / "ERA5_demo.zip").write_bytes(b"zip")
    (data / "ParquetFiles 2017.zip").write_bytes(b"zip")
    (data / "ParquetFiles 2022.zip").write_bytes(b"zip")

    inputs = {"paths": {"smoke_csv": str(data / "ParquetFiles 2022.zip")}}
    sources = selector.detect_smoke_sources(data, inputs)
    decision = selector.select_smoke_route(sources, decoder_available=False)

    assert decision["route_selected"] == "BLOCKED_DECODER_REQUIRED"
    assert decision["operational_fallback_route"] == "v0_parquet_proxy_degraded"
    assert decision["final_scientific_decision"] == "NO-GO_SCIENTIFIC_THRESHOLD"


def test_smoke_route_selector_enables_real_route_when_decoder_available(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import smoke_route_selector as selector  # type: ignore

    data = tmp_path / "Datos"
    data.mkdir(parents=True, exist_ok=True)
    (data / "CAM-GFAS (ADS)").mkdir(parents=True, exist_ok=True)
    (data / "CAM-GFAS (ADS)" / "dummy.grib").write_bytes(b"grib")
    (data / "ERA5_demo.zip").write_bytes(b"zip")
    (data / "ParquetFiles 2017.zip").write_bytes(b"zip")
    (data / "ParquetFiles 2022.zip").write_bytes(b"zip")

    sources = selector.detect_smoke_sources(data, {"paths": {"smoke_csv": str(data / "ParquetFiles 2022.zip")}})
    decision = selector.select_smoke_route(sources, decoder_available=True)

    assert decision["route_selected"] == "v0_gfas_era5_real"
    assert decision["smoke_route_status"] == "SCIENTIFIC_PRIMARY_REAL"
