from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTAINER = ROOT.parent
LAUNCHER = CONTAINER / "02_LAUNCHERS" / "run_modulec_canonical.ps1"
SMOKERUN = ROOT / "tools" / "modulec_structural_smokerun.py"
CONFIG = ROOT / "config" / "module_c_canonical_paths.json"


def test_canonical_launcher_is_single_explicit_smoke_entrypoint() -> None:
    text = LAUNCHER.read_text(encoding="utf-8")
    assert "ValidateSet('smoke')" in text
    assert "MODULEC_OUTPUT_ROOT" not in text
    assert "03_RUNTIMES" in text
    assert "modulec_structural_smokerun.py" in text
    assert "BLOCKED_OUTPUT_ROOT_EXISTS" in text


def test_structural_smokerun_uses_current_head_and_never_scientific_pipeline() -> None:
    text = SMOKERUN.read_text(encoding="utf-8")
    assert "import moduleC_pipeline_v2" not in text
    assert "from moduleC_pipeline_v2" not in text
    assert "--resume" not in text
    cfg = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    assert cfg["EXPECTED_GIT_TOPLEVEL"] == "D:\\GATA_MODULEC_UNIFIED_PROCESS"
    assert cfg["EXPECTED_BASE_SHA"] == "dbcda0b6f3e00d67a7e4a3701e0f2422f87253e9"
    assert cfg["EXPECTED_START_SHA"] == "57aaf4e9c7bb0af545d5653ce8f6cf06cd06af0f"


def test_canonical_config_has_only_effective_gfas_root() -> None:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    roots = cfg["DATA_ROOT_ALLOWED_PREFIXES"]
    assert any(root.endswith("Module C\\Datos\\Datos_RECOVERY_2015_2024_PIPELINE_GRIB") for root in roots)
    assert not any(root.endswith("Module C\\Datos_RECOVERY_2015_2024_PIPELINE_GRIB") for root in roots)
