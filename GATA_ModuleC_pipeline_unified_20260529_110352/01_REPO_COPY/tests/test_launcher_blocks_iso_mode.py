from __future__ import annotations

from pathlib import Path


def test_launcher_blocks_iso_mode_and_forbidden_root():
    repo_root = Path(__file__).resolve().parents[1]
    launcher = repo_root / "pipeline" / "RUN_ModuleC_Pipeline_OSGeo4W.cmd"
    text = launcher.read_text(encoding="utf-8", errors="replace")

    assert "RUNMODE=ISO" not in text
    assert "BLOCKED_FORBIDDEN_CODE_ROOT" in text
    assert "ISO_DIAGNOSTIC_REFERENCE_ONLY" in text
    assert "PATH_SCOPE_GUARD" in text
