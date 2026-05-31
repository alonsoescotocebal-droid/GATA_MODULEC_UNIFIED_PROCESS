from __future__ import annotations

import sys
from pathlib import Path


def test_parquet_proxy_is_degraded_and_not_scientific_go(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import smoke_route_selector as selector  # type: ignore

    data = tmp_path / "Datos"
    data.mkdir(parents=True, exist_ok=True)
    (data / "ParquetFiles 2017.zip").write_bytes(b"zip")
    (data / "ParquetFiles 2022.zip").write_bytes(b"zip")

    sources = selector.detect_smoke_sources(data, {"paths": {"smoke_csv": str(data / "ParquetFiles 2022.zip")}})
    decision = selector.select_smoke_route(sources, decoder_available=False)

    assert decision["route_selected"] == "v0_parquet_proxy_degraded"
    assert decision["allowed_use"] == "diagnostic_only"
    assert decision["final_scientific_decision"] == "NO-GO_SCIENTIFIC_THRESHOLD"
