from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTAINER = ROOT.parent
LAUNCHER = CONTAINER / "02_LAUNCHERS" / "run_modulec_canonical.ps1"
SMOKERUN = ROOT / "tools" / "modulec_structural_smokerun.py"
CONFIG = ROOT / "config" / "module_c_canonical_paths.json"


def test_canonical_launcher_is_single_explicit_structural_entrypoint() -> None:
    text = LAUNCHER.read_text(encoding="utf-8")
    assert "ValidateSet('Preflight','Smoke','Full')" in text
    assert "MODULEC_OUTPUT_ROOT" in text
    assert "03_RUNTIMES" in text
    assert "modulec_canonical_structural_run.py" in text
    assert "path_scope_guard.py" in text
    assert "BLOCKED_OUTPUT_ROOT_EXISTS" in text


def test_structural_smokerun_uses_current_head_and_never_scientific_pipeline() -> None:
    text = SMOKERUN.read_text(encoding="utf-8")
    assert "import moduleC_pipeline_v2" not in text
    assert "from moduleC_pipeline_v2" not in text
    assert "--resume" not in text
    cfg = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    assert cfg["EXPECTED_GIT_TOPLEVEL"] == "D:\\GATA_MODULEC_UNIFIED_PROCESS"
    assert cfg["EXPECTED_BASE_SHA"] == "5fc85e83b092559fe332f1aa5006b7d33d04b727"
    assert cfg["EXPECTED_START_SHA"] == "57aaf4e9c7bb0af545d5653ce8f6cf06cd06af0f"


def test_canonical_config_has_only_effective_gfas_root() -> None:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    roots = cfg["DATA_ROOT_ALLOWED_PREFIXES"]
    assert any(root.endswith("Module C\\Datos\\Datos_RECOVERY_2015_2024_PIPELINE_GRIB") for root in roots)
    assert not any(root.endswith("Module C\\Datos_RECOVERY_2015_2024_PIPELINE_GRIB") for root in roots)
