from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path


def test_scientific_gate_blocks_when_smoke_route_is_blocked_decoder_required(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    output_root = tmp_path / "03_outputs"
    (output_root / "tables").mkdir(parents=True, exist_ok=True)
    (output_root / "brief" / "causal_matrix").mkdir(parents=True, exist_ok=True)
    (output_root / "qa").mkdir(parents=True, exist_ok=True)

    (output_root / "tables" / "smoke_days_unit_2015_2024.csv").write_text(
        "unit_id;year;smoke_days\nA;2015;10\nB;2015;20\n",
        encoding="utf-8",
    )
    (output_root / "tables" / "IECH_unit_2015_2024.csv").write_text(
        "unit_id;year;smoke_days;smoke_hours_equiv;pop;expo_person_hours;IECH\n"
        "A;2015;10;240;100;24000;180\n"
        "B;2015;20;480;200;96000;360\n",
        encoding="utf-8",
    )
    (output_root / "tables" / "IECH_unit_2015_2024_mean.csv").write_text(
        "unit_id;IECH_mean_2015_2024\nA;180\nB;360\n",
        encoding="utf-8",
    )
    (output_root / "brief" / "causal_matrix" / "causal_matrix_IECH_NUTS3.csv").write_text(
        "unit_id;qa_flag;missing_components;threshold_gate_status\nA;OK;;THRESHOLD_DEFINED_AS_INDEXED_METHOD\n",
        encoding="utf-8",
    )
    (output_root / "brief" / "Brief_Politica_IECH_2030.md").write_text("Brief baseline text.\n", encoding="utf-8")

    inputs_payload = {
        "paths": {"smoke_csv": "D:\\fake\\ParquetFiles 2022.zip"},
        "meta": {
            "smoke_route_selected": "BLOCKED_DECODER_REQUIRED",
            "smoke_route_decision": "BLOCKED_DECODER_REQUIRED",
        },
    }
    (output_root / "qa" / "inputs_resolved.json").write_text(json.dumps(inputs_payload), encoding="utf-8")

    gate_script = repo_root / "pipeline" / "scientific_threshold_gate.py"
    proc = subprocess.run(
        [sys.executable, str(gate_script), "--output-root", str(output_root), "--repo-root", str(repo_root)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

    gate_tsv = output_root / "qa" / "scientific_validation_gate.tsv"
    with gate_tsv.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    route_rows = [r for r in rows if r.get("threshold_id") == "SMOKE-ROUTE-001"]
    assert route_rows, "Missing SMOKE-ROUTE-001 gate row"
    assert route_rows[0]["gate_status"] == "BLOCKED_DECODER_REQUIRED"

    closure_md = (output_root / "deliverables_step9" / "runtime_scientific_closure_decision.md").read_text(encoding="utf-8")
    assert "NO-GO_SCIENTIFIC_THRESHOLD" in closure_md
