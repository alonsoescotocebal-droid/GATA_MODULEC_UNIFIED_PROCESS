from __future__ import annotations

from pathlib import Path


def test_scientific_closure_includes_smoke_route_scope_limitation():
    repo_root = Path(__file__).resolve().parents[1]
    gate = (repo_root / "pipeline" / "scientific_threshold_gate.py").read_text(encoding="utf-8", errors="replace")

    assert "def read_smoke_route_scope" in gate
    assert "## Smoke Route Scope" in gate
    assert "smoke_route_reason" in gate
    assert "smoke_route_allowed_use" in gate
    assert "smoke_route_forbidden_use" in gate
