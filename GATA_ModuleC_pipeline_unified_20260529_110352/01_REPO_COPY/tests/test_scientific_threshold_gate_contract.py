from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_scientific_threshold_gate_writes_contract_outputs(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    output_root = tmp_path / "03_outputs"

    _write_text(
        output_root / "tables" / "smoke_days_unit_2015_2024.csv",
        "unit_id;year;smoke_days\nA;2015;10\nB;2015;10\n",
    )
    _write_text(
        output_root / "tables" / "IECH_unit_2015_2024_mean.csv",
        "unit_id;IECH_mean_2015_2024\nA;100\nB;100\n",
    )
    _write_text(
        output_root / "brief" / "causal_matrix" / "causal_matrix_IECH_NUTS3.csv",
        "unit_id;qa_flag;missing_components;threshold_gate_status\nA;OK;;THRESHOLD_DEFINED_AS_INDEXED_METHOD\n",
    )
    _write_text(
        output_root / "brief" / "Brief_Politica_IECH_2030.md",
        "Brief base line.\n",
    )

    gate_script = repo_root / "pipeline" / "scientific_threshold_gate.py"
    proc = subprocess.run(
        [sys.executable, str(gate_script), "--output-root", str(output_root), "--repo-root", str(repo_root)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

    assert (output_root / "qa" / "scientific_validation_gate.tsv").exists()
    assert (output_root / "qa" / "scientific_claim_gate.tsv").exists()
    assert (output_root / "qa" / "scientific_threshold_evidence_register.tsv").exists()
    assert (output_root / "qa" / "blocked_claims_register.tsv").exists()
    assert (output_root / "qa" / "causal_matrix_scientific_gate_audit.tsv").exists()
    assert (output_root / "qa" / "brief_claim_scientific_gate_audit.tsv").exists()
    assert (output_root / "deliverables_step9" / "runtime_scientific_closure_decision.md").exists()
