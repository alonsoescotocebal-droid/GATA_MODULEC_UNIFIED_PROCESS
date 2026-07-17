from pathlib import Path
import sys


def test_wrb_zero_burn_is_not_applicable_not_invented(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / 'pipeline' / 'RUN_QGIS' / 'STEP7_MATRIZ_CAUSAL'))
    import step7_matriz_causal as step7  # type: ignore

    row = step7._wrb_empty_row('U1', tmp_path / 'wrb.tif', 'zero burn', step7.WRB_STATUS_NOT_APPLICABLE_ZERO_BURN, 0, 1)
    assert row[1] == ''
    assert row[2] == ''
    assert row[7] == step7.WRB_METHOD_BURNED_AREA_OVERLAY
    assert row[8] == step7.WRB_STATUS_NOT_APPLICABLE_ZERO_BURN
    assert row[9] == 1

def test_wrb_zero_burn_status_does_not_create_causal_hold(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / 'pipeline' / 'RUN_QGIS' / 'STEP7_MATRIZ_CAUSAL'))
    import step7_matriz_causal as step7  # type: ignore

    def write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
        lines = [','.join(header)]
        for row in rows:
            lines.append(','.join(str(v) for v in row))
        path.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    smoke_csv = tmp_path / 'smoke.csv'
    pop_csv = tmp_path / 'pop.csv'
    recurrence_csv = tmp_path / 'rec.csv'
    iech_csv = tmp_path / 'iech.csv'
    scen_csv = tmp_path / 'scen.csv'
    wrb_csv = tmp_path / 'wrb.csv'
    terr_csv = tmp_path / 'terr.csv'
    out_csv = tmp_path / 'causal.csv'

    write_csv(smoke_csv, ['unit_id', 'smoke_days'], [['U1', 12], ['U1', 18]])
    write_csv(pop_csv, ['unit_id', 'pop_2020_sum', 'pop_2030_sum'], [['U1', 1000, 1100]])
    write_csv(recurrence_csv, ['unit_id', 'total_burn_ha_2015_2024', 'years_area_gt_p75', 'n_events_gt_1000ha', 'recurrence_class'], [['U1', 0, 0, 0, 'LOW']])
    write_csv(iech_csv, ['unit_id', 'population_smoke_burden_proxy_mean_2015_2024'], [['U1', 50]])
    write_csv(scen_csv, ['unit_id', 'population_smoke_burden_proxy_S0_mean_2026_2030', 'population_smoke_burden_proxy_S1_mean_2026_2030', 'delta_population_smoke_burden_proxy_S1_minus_S0'], [['U1', 40, 30, -10]])
    write_csv(wrb_csv, ['unit_id', 'dominant_wrb_class', 'dominant_wrb_share', 'wrb_context_note', 'wrb_source', 'wrb_missing_flag', 'wrb_method', 'wrb_coverage_status', 'wrb_not_applicable_flag'], [['U1', '', '', 'Sin interseccion quemada 2015-2024 verificada; WRB no aplicable para interpretacion de area quemada.', 'wrb.tif', 0, step7.WRB_METHOD_BURNED_AREA_OVERLAY, step7.WRB_STATUS_NOT_APPLICABLE_ZERO_BURN, 1]])
    write_csv(terr_csv, ['unit_id', 'built_up_proxy', 'forest_proxy', 'shrubland_proxy', 'wui_proxy', 'territorial_missing_flag'], [['U1', 1, 2, 3, 4, 0]])

    rows = step7.build_causal_matrix(tmp_path, 'MUNICIPIO', smoke_csv, pop_csv, recurrence_csv, iech_csv, scen_csv, wrb_csv, terr_csv, out_csv)

    assert rows[0]['missing_components'] == ''
    assert rows[0]['qa_flag'] == 'OK'
    assert rows[0]['threshold_gate_status'] == 'THRESHOLD_DEFINED_AS_INDEXED_METHOD'
    assert rows[0]['causal_matrix_scientific_status'] == 'THRESHOLD_DEFINED_AS_INDEXED_METHOD'
    assert 'sin interseccion quemada' not in step7.WRB_FORBIDDEN_NOTE_TOKENS
