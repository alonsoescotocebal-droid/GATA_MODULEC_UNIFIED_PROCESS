from pathlib import Path

from pipeline.screening_r10c import apply_canonical_screening, classify_band, compare_variant, tie_aware_fractional_rank, write_r10c_qa


def _rows(burdens=(1.0, 2.0, 3.0), recurrence=(0.2, 0.5, 0.8)):
    return [
        {
            "unit_id": f"U{index}",
            "population_smoke_day_burden_proxy_mean_2015_2024": burden,
            "recurrence_score": rec,
            "recurrence_temporal_rank": rec,
            "recurrence_reburn_rank": rec,
            "recurrence_class": classify_band(rec),
            "policy_priority": "MEDIUM_PRIORITY",
            "missing_components": "WUI|WRB",
            "population_2020": 100.0 + index,
            "smoke_days_mean_2015_2024": 10.0 + index,
        }
        for index, (burden, rec) in enumerate(zip(burdens, recurrence))
    ]


def test_scr_01_burden_changes_score_with_recurrence_fixed():
    rows = apply_canonical_screening(_rows(burdens=(1.0, 2.0, 3.0), recurrence=(0.5, 0.5, 0.5)), "NUTS3")
    assert [row["screening_priority_score"] for row in rows] == [0.25, 0.5, 0.75]
    assert [row["policy_priority"] for row in rows] == ["MONITOR", "MEDIUM_PRIORITY", "HIGH_PRIORITY"]


def test_scr_02_recurrence_changes_score_with_burden_fixed():
    rows = apply_canonical_screening(_rows(burdens=(2.0, 2.0, 2.0), recurrence=(0.1, 0.5, 0.9)), "NUTS3")
    assert [row["screening_priority_score"] for row in rows] == [0.25, 0.5, 0.75]


def test_scr_04_tie_aware_burden_rank():
    assert tie_aware_fractional_rank([1.0, 1.0, 3.0]) == [0.25, 0.25, 1.0]


def test_scr_05_tie_aware_recurrence_rank():
    rows = apply_canonical_screening(_rows(burdens=(1.0, 1.0, 1.0), recurrence=(0.2, 0.2, 0.8)), "NUTS3")
    assert [row["recurrence_priority_rank"] for row in rows] == [0.25, 0.25, 1.0]


def test_scr_06_levels_are_ranked_separately():
    nuts = apply_canonical_screening(_rows(burdens=(1.0, 2.0), recurrence=(0.2, 0.8)), "NUTS3")
    muni = apply_canonical_screening(_rows(burdens=(100.0, 200.0), recurrence=(0.2, 0.8)), "MUNICIPIO")
    assert [row["burden_priority_rank"] for row in nuts] == [0.0, 1.0]
    assert [row["burden_priority_rank"] for row in muni] == [0.0, 1.0]
    assert muni[0]["screening_claim_status"] == "REGIONAL_SMOKE_INFORMED_MUNICIPAL_SCREENING"


def test_scr_07_canonical_weights_are_equal_and_visible():
    rows = apply_canonical_screening(_rows(), "NUTS3")
    assert rows[0]["screening_method"].startswith("R10_C_TWO_DIMENSIONAL")
    assert rows[0]["screening_priority_score"] == 0.0
    assert rows[0]["burden_priority_rank"] == 0.0
    assert rows[0]["recurrence_priority_rank"] == 0.0


def test_scr_08_fixed_bands_use_one_third_boundaries():
    assert classify_band(0.0) == "LOW"
    assert classify_band(1.0 / 3.0) == "MEDIUM"
    assert classify_band(2.0 / 3.0) == "HIGH"


def test_scr_09_contextual_hold_does_not_block_core_screening():
    row = apply_canonical_screening(_rows(burdens=(2.0,), recurrence=(0.5,)), "NUTS3")[0]
    assert row["screening_core_status"] == "PASS"
    assert row["contextual_completeness_status"] == "CONTEXTUAL_HOLD"


def test_scr_10_no_recurrence_class_hard_gate_in_contract_source():
    source = Path(__file__).parents[1].joinpath("pipeline", "screening_r10c.py").read_text(encoding="utf-8")
    assert "if recurrence_class in" not in source
    assert "R10C_WEIGHTS = (0.50, 0.50)" in source


def test_scr_11_p80_is_legacy_only():
    source = _rows(burdens=(1.0, 2.0, 100.0), recurrence=(0.8, 0.5, 0.2))
    rows = apply_canonical_screening(source, "NUTS3")
    source[0]["policy_priority"] = "HIGH_PRIORITY"
    changed_legacy_input = apply_canonical_screening(source, "NUTS3")
    assert rows[0]["legacy_burden_p80_flag"] == 0
    assert rows[2]["legacy_burden_p80_flag"] == 1
    assert [row["screening_priority_score"] for row in rows] == [row["screening_priority_score"] for row in changed_legacy_input]


def test_scr_12_13_14_downstream_components_are_not_primary_columns():
    rows = apply_canonical_screening(_rows(), "NUTS3")
    assert all("smoke_days" not in row["screening_method"] for row in rows)
    assert all("population_2020" not in row["screening_method"] for row in rows)
    assert all("reburn" not in row["screening_method"].lower() for row in rows)


def test_scr_15_qa_and_transport_sensitivity_are_written(tmp_path):
    rows = apply_canonical_screening(_rows(), "NUTS3")
    rows_muni = apply_canonical_screening(_rows(), "MUNICIPIO")
    tables = tmp_path / "tables"
    tables.mkdir()
    daily_header = "unit_id;year;smoke_day_score;transport_proxy_12h_mean;transport_proxy_12h_max;transport_proxy_24h_mean;transport_proxy_24h_max;transport_proxy_48h_mean;transport_proxy_48h_max\n"
    daily_rows = "".join(
        f"U{i};2015;{0.001 + i};{0.001 + i};{0.001 + i};{0.001 + i};{0.001 + i};{0.001 + i};{0.001 + i}\n"
        for i in range(3)
    )
    for name in ("smoke_day_score_nuts3_daily.csv", "smoke_day_score_municipio_daily.csv"):
        (tables / name).write_text(daily_header + daily_rows, encoding="utf-8")
    pop_header = "unit_id;pop_2015_sum;pop_2020_sum;pop_2025_sum\n"
    pop_rows = "".join(f"U{i};100;100;100\n" for i in range(3))
    for name in ("pop_unit_2015_2025_2030.csv", "pop_municipio_2015_2025_2030.csv"):
        (tables / name).write_text(pop_header + pop_rows, encoding="utf-8")
    qa_dir = tmp_path / "qa"
    write_r10c_qa(qa_dir, {"NUTS3": rows, "MUNICIPIO": rows_muni})
    assert (qa_dir / "r10_c_legacy_screening_dominance_audit.tsv").exists()
    transport = (qa_dir / "r10_c_smoke_transport_sensitivity_propagation.tsv").read_text(encoding="utf-8")
    assert "24h_75_25_CANONICAL" in transport
    assert "variant_smoke_days_total" in transport
    independence = (qa_dir / "r10_c_dimension_independence_audit.tsv").read_text(encoding="utf-8")
    assert "legacy_recurrence_only_class_agreement\t0.9583333333333334" not in independence


def test_scr_16_to_19_contextual_fields_do_not_change_core_score():
    base = _rows()
    baseline = apply_canonical_screening(base, "NUTS3")
    for key, value in (("wui_proxy", 999.0), ("dominant_wrb_class", "OTHER"), ("aq_concordance", "PASS"), ("population_smoke_day_burden_proxy_S1_mean_2026_2030", 999999.0)):
        changed = _rows()
        for row in changed:
            row[key] = value
        screened = apply_canonical_screening(changed, "NUTS3")
        assert [row["screening_priority_score"] for row in screened] == [row["screening_priority_score"] for row in baseline]


def test_scr_20_municipal_claim_is_not_direct_atmospheric_signal():
    row = apply_canonical_screening(_rows(burdens=(2.0,), recurrence=(0.5,)), "MUNICIPIO")[0]
    assert row["screening_claim_status"] == "REGIONAL_SMOKE_INFORMED_MUNICIPAL_SCREENING"
    assert row["smoke_signal_resolution"] == "REGIONAL_NUTS3_SIGNAL_ALLOCATED_TO_MUNICIPALITY"
    assert row["recurrence_signal_resolution"] == "DIRECT_MUNICIPAL_FIRE_FOOTPRINT"
    assert "ATMOSPHERIC_RISK" not in row["screening_claim_status"]


def test_scr_21_50_50_sensitivity_reproduces_canonical_exactly():
    rows = apply_canonical_screening(_rows(), "NUTS3")
    scores = [0.5 * row["burden_priority_rank"] + 0.5 * row["recurrence_priority_rank"] for row in rows]
    metrics = compare_variant(rows, scores)
    assert abs(metrics["screening_score_spearman_to_canonical"] - 1.0) < 1e-12
    assert metrics["class_agreement_fraction"] == 1.0
    assert metrics["HIGH_class_jaccard"] == 1.0
    assert metrics["top5_overlap"] == 1.0
    assert metrics["units_changing_class"] == 0


def test_scr_22_legacy_fields_are_diagnostic_only():
    rows = apply_canonical_screening(_rows(), "NUTS3")
    assert all("legacy_policy_priority" in row for row in rows)
    assert all("legacy_burden_p80_flag" in row for row in rows)
    assert all(row["screening_method"].startswith("R10_C_") for row in rows)


def test_scr_03_and_scr_09_both_dimensions_and_fixed_bands_are_effective():
    rows = apply_canonical_screening(_rows(burdens=(1.0, 2.0, 3.0, 4.0, 5.0), recurrence=(0.1, 0.2, 0.3, 0.4, 0.5)), "NUTS3")
    assert len({row["burden_priority_rank"] for row in rows}) > 1
    assert len({row["recurrence_priority_rank"] for row in rows}) > 1
    assert set(row["policy_priority"] for row in rows) == {"MONITOR", "MEDIUM_PRIORITY", "HIGH_PRIORITY"}
