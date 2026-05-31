from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_step7_module():
    repo_root = Path(__file__).resolve().parents[1]
    mod_path = repo_root / "pipeline" / "RUN_QGIS" / "STEP7_MATRIZ_CAUSAL" / "step7_matriz_causal.py"
    spec = importlib.util.spec_from_file_location("step7_matriz_causal", str(mod_path))
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_step7_smoke_homogeneous_helper_blocks(tmp_path):
    mod = _load_step7_module()
    smoke = tmp_path / "smoke_days_unit_2015_2024.csv"
    smoke.write_text(
        "unit_id;year;smoke_days\n"
        "U1;2015;10\n"
        "U2;2015;10\n",
        encoding="utf-8",
    )
    assert mod._smoke_spatial_homogeneous(smoke) is True


def test_step7_iech_cancellation_helper_blocks(tmp_path):
    mod = _load_step7_module()
    iech = tmp_path / "IECH_unit_2015_2024.csv"
    iech.write_text(
        "unit_id;year;smoke_days;smoke_hours_equiv;pop;expo_person_hours;IECH\n"
        "U1;2015;10;240;100;24000;240\n"
        "U2;2015;20;480;200;96000;480\n",
        encoding="utf-8",
    )
    assert mod._iech_population_cancellation(iech) is True
