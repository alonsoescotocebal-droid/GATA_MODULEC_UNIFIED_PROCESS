from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.phase3_objective_closure import _semantic_audits, _feasibility_audits


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_phase3_semantic_contract_blocks_formal_claims(tmp_path):
    root = tmp_path / "out"
    _write(root / "tables" / "IECH_unit_2015_2024.csv", "unit_id;population_smoke_burden_proxy\nN1;10\n")
    _write(root / "tables" / "territorial_context_nuts3.csv", "unit_id;wui_proxy\nN1;2\n")
    _write(root / "tables" / "IECH_scenarios_2026_2030.csv", "unit_id;scenario\nN1;S1\n")
    _write(root / "tables" / "IECH_municipio_2015_2024.csv", "unit_id;population_smoke_burden_proxy\nM1;10\n")
    _write(root / "brief" / "causal_matrix" / "causal_matrix_IECH_NUTS3.csv", "unit_id;qa_flag\nN1;OK\n")

    _semantic_audits(root)
    rows = (root / "qa" / "objective_semantic_contract_audit.tsv").read_text(encoding="utf-8")
    assert "BLOCKED_NORMALIZED_IECH_CLAIM" in rows
    assert "HOLD_FORMAL_WUI" in rows
    assert "TERRITORIAL_SCREENING_ASSOCIATION" in rows
    assert "NORMATIVE_ASSUMPTION" in rows


def test_phase3_feasibility_retains_canonical_proxy(tmp_path):
    root = tmp_path / "out"
    _write(root / "tables" / "smoke_day_score_nuts3_daily.csv", "unit_id;year;smoke_days\nN1;2015;2\n")
    _write(root / "tables" / "pop_unit_2015_2025_2030.csv", "unit_id;pop_2020_sum\nN1;10\n")
    _feasibility_audits(root, {"paths": {"smoke_effective_data_root": "recovery"}})
    text = (root / "qa" / "population_weighted_smoke_feasibility.tsv").read_text(encoding="utf-8")
    assert "SPATIAL_POPULATION_WEIGHTED_PROXY_NOT_IMPLEMENTED" in text
    assert "CURRENT_POPULATION_BURDEN_PROXY_RETAINED" in text
