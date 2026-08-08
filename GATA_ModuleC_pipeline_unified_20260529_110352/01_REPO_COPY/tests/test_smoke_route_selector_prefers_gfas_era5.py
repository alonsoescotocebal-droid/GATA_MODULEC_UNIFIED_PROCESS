from __future__ import annotations

import sys
from pathlib import Path


def test_smoke_route_selector_prefers_gfas_era5_over_parquet_final(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import smoke_route_selector as selector  # type: ignore

    data = tmp_path / "Module C" / "Datos"
    recovery = tmp_path / "Module C" / "Datos_RECOVERY_2015_2024_PIPELINE_GRIB"
    data.mkdir(parents=True, exist_ok=True)
    recovery.mkdir(parents=True, exist_ok=True)
    (recovery / "dummy.grib").write_bytes(b"grib")
    (recovery / "_grib_summary.csv").write_text("file,minDate,message_count,pm_stride_hint\nx.grib,20150101,365,1\n", encoding="utf-8")
    (recovery / "ERA5_demo.zip").write_bytes(b"zip")
    (data / "ParquetFiles 2017.zip").write_bytes(b"zip")
    (data / "ParquetFiles 2022.zip").write_bytes(b"zip")

    inputs = {"paths": {"smoke_csv": str(data / "ParquetFiles 2022.zip")}}
    sources = selector.detect_smoke_sources(data, inputs)
    decision = selector.select_smoke_route(sources, decoder_available=False)

    assert decision["route_selected"] == "BLOCKED_DECODER_REQUIRED"
    assert sources["effective_source_is_recovery"] is True
    assert decision["operational_fallback_route"] == "v0_parquet_proxy_degraded"
    assert decision["final_scientific_decision"] == "NO-GO_SCIENTIFIC_THRESHOLD"


def test_smoke_route_selector_enables_real_route_when_decoder_available(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import smoke_route_selector as selector  # type: ignore

    data = tmp_path / "Module C" / "Datos"
    recovery = tmp_path / "Module C" / "Datos_RECOVERY_2015_2024_PIPELINE_GRIB"
    data.mkdir(parents=True, exist_ok=True)
    recovery.mkdir(parents=True, exist_ok=True)
    (recovery / "dummy.grib").write_bytes(b"grib")
    (recovery / "_grib_summary.csv").write_text("file,minDate,message_count,pm_stride_hint\nx.grib,20150101,365,1\n", encoding="utf-8")
    (recovery / "ERA5_demo.zip").write_bytes(b"zip")
    (data / "ParquetFiles 2017.zip").write_bytes(b"zip")
    (data / "ParquetFiles 2022.zip").write_bytes(b"zip")

    sources = selector.detect_smoke_sources(data, {"paths": {"smoke_csv": str(data / "ParquetFiles 2022.zip")}})
    decision = selector.select_smoke_route(sources, decoder_available=True)

    assert decision["route_selected"] == "v0_gfas_era5_real"
    assert decision["smoke_route_status"] == "SCIENTIFIC_PRIMARY_REAL"


def test_smoke_route_selector_blocks_legacy_direct_sources_even_if_decoder_available(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import smoke_route_selector as selector  # type: ignore

    data = tmp_path / "Datos"
    data.mkdir(parents=True, exist_ok=True)
    legacy_gfas = data / "CAM-GFAS (ADS)"
    legacy_gfas.mkdir(parents=True, exist_ok=True)
    (legacy_gfas / "dummy.grib").write_bytes(b"grib")
    (legacy_gfas / "_grib_summary.csv").write_text("file,minDate,message_count,pm_stride_hint\nx.grib,20150101,365,1\n", encoding="utf-8")
    (data / "ERA5_demo.zip").write_bytes(b"zip")

    sources = selector.detect_smoke_sources(data, {"paths": {"smoke_csv": str(data / "ParquetFiles 2022.zip")}})
    decision = selector.select_smoke_route(sources, decoder_available=True)

    assert sources["effective_source_is_recovery"] is False
    assert decision["route_selected"] == "NO-GO_SMOKE_ROUTE"
    assert decision["smoke_route_decision"] == "BLOCKED_FORBIDDEN_PRIMARY_SMOKE_SOURCE"


def test_recovered_era5_validated_directory_pairs_with_recovered_gfas(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import smoke_route_selector as selector  # type: ignore

    modulec_root = tmp_path / "Module C"
    data = modulec_root / "Datos"
    gfas_root = modulec_root / "Datos_RECOVERY_2015_2024_PIPELINE_GRIB"
    gfas_root.mkdir(parents=True)
    (gfas_root / "pm2p5fire_2015.grib").write_bytes(b"gfas")
    era5_root = modulec_root / "Datos_RECOVERY_ERA5_2015_2024_R10A2" / "validated"
    era5_root.mkdir(parents=True)
    (era5_root / "ERA5_UV_2015.grib").write_bytes(b"era5")
    (gfas_root / "ERA5_000_2015_2024.zip").write_bytes(b"legacy")

    sources = selector.detect_smoke_sources(data, {"paths": {}})

    assert sources["gfas_exists"] is True
    assert sources["era5_exists"] is True
    assert Path(sources["era5_zip"]) == era5_root
    assert sources["effective_source_is_recovery"] is True
