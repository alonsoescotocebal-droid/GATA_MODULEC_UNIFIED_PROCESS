from pathlib import Path

from pipeline import qa_gate_v2
from pipeline import scientific_threshold_gate
from pipeline import validate_modulec_objectives_canon as objectives
from pipeline.screening_r10c import apply_canonical_screening


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_wui_fixture(root: Path, *, forbidden_brief: str = "") -> None:
    _write(
        root / "tables" / "territorial_context_nuts3.csv",
        "unit_id;built_up_proxy;forest_proxy;shrubland_proxy;wui_proxy;"
        "territorial_indicator_type;territorial_proxy_status;formal_wui_claim_status;"
        "landcover_source;formal_wui_method;building_vegetation_spatial_relation;formal_wui_source_status\n"
        "N1;10;2;3;50;BUILT_UP_FUEL_TERRITORIAL_PROXY;AVAILABLE_AS_CONTEXT;"
        "HOLD_FORMAL_WUI;GHSL_BUILT_2020:built.zip,fuel_proxy_from:recurrence.csv;"
        "NOT_IMPLEMENTED;FALSE;NOT_SUPPORTED_BY_CURRENT_AUTHORIZED_INPUTS\n",
    )
    _write(
        root / "qa" / "objective_semantic_contract_audit.tsv",
        "contract\tvalue\tstatus\tdetail\n"
        "territorial_indicator_type\tBUILT_UP_FUEL_TERRITORIAL_PROXY\tPASS\tproxy\n"
        "formal_wui_claim_status\tHOLD_FORMAL_WUI\tHOLD\tformal relation absent\n"
        "territorial_proxy_allowed_use\tCONTEXTUAL_TERRITORIAL_DESCRIPTOR\tPASS\tproxy only\n"
        "formal_wui_source_status\tNOT_SUPPORTED_BY_CURRENT_AUTHORIZED_INPUTS\tHOLD\tinputs absent\n",
    )
    if forbidden_brief:
        _write(root / "brief" / "Brief_Politica_IECH_2030.md", forbidden_brief)


def test_d1_01_positive_proxy_is_not_formal_wui(tmp_path):
    root = tmp_path / "out"
    _write_wui_fixture(root)

    proxy_ok, _ = objectives._check_territorial_proxy_quality(root)
    formal_ok, detail = objectives._check_formal_wui_quality(root)

    assert proxy_ok is True
    assert formal_ok is False
    assert "HOLD_FORMAL_WUI" in detail


def test_d1_02_d1_04_oc07_holds_when_formal_wui_is_on_hold(tmp_path):
    root = tmp_path / "out"
    _write_wui_fixture(root)

    ok, reason = objectives.objective_specific_check("OC-07", root, {})

    assert ok is False
    assert "FORMAL_WUI_NOT_SUPPORTED_BY_CURRENT_AUTHORIZED_INPUTS" in reason
    assert "BUILT_UP_FUEL_TERRITORIAL_PROXY" in reason


def test_d1_03_and_d1_10_proxy_metadata_is_explicit_context_only(tmp_path):
    root = tmp_path / "out"
    _write_wui_fixture(root)

    status = objectives.read_wui_semantic_status(root)

    assert status["territorial_proxy_available"] is True
    assert status["formal_wui_available"] is False
    assert status["territorial_indicator_type"] == "BUILT_UP_FUEL_TERRITORIAL_PROXY"
    assert status["territorial_proxy_status"] == "AVAILABLE_AS_CONTEXT"


def test_d1_05_and_d1_06_qa_gate_holds_formal_wui_not_proxy(tmp_path):
    root = tmp_path / "out"
    _write_wui_fixture(root)

    _decision, _summary, holds, _rows = qa_gate_v2.evaluate_output_root(root)

    assert "HOLD FORMAL WUI" in holds
    assert not any("GO" == value for value in holds)


def test_d1_07_scientific_hold_is_not_execution_failure(tmp_path):
    root = tmp_path / "out"
    _write_wui_fixture(root)

    status, detail, metrics = scientific_threshold_gate.evaluate_formal_wui(root)

    assert status == "BLOCKED_FORMAL_WUI_CLAIM"
    assert metrics["building_vegetation_spatial_relation"] == 0
    assert "HOLD_OC07" in detail


def test_d1_08_r10c_score_is_independent_of_wui_context():
    rows = [
        {
            "unit_id": "N1",
            "population_smoke_day_burden_proxy_mean_2015_2024": 1.0,
            "recurrence_score": 0.2,
            "recurrence_class": "LOW",
        },
        {
            "unit_id": "N2",
            "population_smoke_day_burden_proxy_mean_2015_2024": 2.0,
            "recurrence_score": 0.8,
            "recurrence_class": "HIGH",
        },
    ]
    baseline = apply_canonical_screening(rows, "NUTS3")
    contextual = [dict(row, wui_proxy=999999.0) for row in rows]

    changed = apply_canonical_screening(contextual, "NUTS3")

    assert scientific_threshold_gate.R10_C_CANONICAL_SCORE_DEPENDS_ON_WUI is False
    assert [row["screening_priority_score"] for row in baseline] == [
        row["screening_priority_score"] for row in changed
    ]


def test_d1_09_forbidden_formal_wui_claims_are_blocked(tmp_path):
    root = tmp_path / "out"
    _write_wui_fixture(root, forbidden_brief="This is a formal WUI risk exposure prioritization.")

    status, hits = scientific_threshold_gate.audit_formal_wui_claims(root)

    assert status == "BLOCKED_FORMAL_WUI_CLAIM"
    assert hits
    assert any("WUI_RISK" in hit or "WUI_EXPOSURE" in hit for hit in hits)
