from __future__ import annotations

import json
import sys
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import path_scope_guard as mod  # type: ignore

    return mod


def test_load_config_accepts_recovery_root_prefixes(tmp_path):
    mod = _load_module()
    config_path = tmp_path / "module_c_canonical_paths.json"
    payload = {
        "EXPECTED_REPO_ROOT": r"D:\repo",
        "EXPECTED_BRANCH": "main",
        "EXPECTED_BASE_SHA": "abc123",
        "FORBIDDEN_CODE_ROOT": r"D:\forbidden",
        "DATA_ROOT_ALLOWED_PREFIX": r"D:\Module C\Datos",
        "DATA_ROOT_ALLOWED_PREFIXES": [
            r"D:\Module C\Datos",
            r"D:\Module C\Datos_RECOVERY_2015_2024_PIPELINE_GRIB",
        ],
        "OUTPUT_ROOT_ALLOWED_PREFIX": r"D:\runtimes",
    }
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    cfg = mod.load_config(config_path)
    prefixes = mod._allowed_data_prefixes(cfg)

    assert any("datos_recovery_2015_2024_pipeline_grib" in str(p).lower() for p in prefixes)
