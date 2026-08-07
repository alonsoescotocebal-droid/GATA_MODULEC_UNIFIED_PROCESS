from pathlib import Path
import sys


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def test_causal_matrix_uses_canonical_proxy_means(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / 'pipeline' / 'RUN_QGIS' / 'STEP7_MATRIZ_CAUSAL'))
    import step7_matriz_causal as step7  # type: ignore

    _write(tmp_path / 'smoke.csv', 'unit_id;year;smoke_days\nU1;2015;1\n')
    _write(tmp_path / 'pop.csv', 'unit_id;pop_2020_sum;pop_2030_sum\nU1;10;10\n')
    _write(tmp_path / 'rec.csv', 'unit_id;total_burn_ha_2015_2024;years_area_gt_p75;n_events_gt_1000ha;recurrence_class\nU1;0;0;0;LOW\n')
    _write(tmp_path / 'iech.csv', 'unit_id;population_smoke_day_burden_proxy_mean_2015_2024\nU1;321\n')
    _write(tmp_path / 'scen.csv', 'unit_id;population_smoke_day_burden_proxy_S0_mean_2026_2030;population_smoke_day_burden_proxy_S1_mean_2026_2030;delta_population_smoke_day_burden_proxy_S1_minus_S0\nU1;400;300;-100\n')
    _write(tmp_path / 'wrb.csv', f'unit_id;dominant_wrb_class;dominant_wrb_share;top_wrb_classes;wrb_context_note;wrb_source;wrb_missing_flag;wrb_method;wrb_coverage_status;wrb_not_applicable_flag\nU1;;;;na;src;0;{step7.WRB_METHOD_BURNED_AREA_OVERLAY};{step7.WRB_STATUS_NOT_APPLICABLE_ZERO_BURN};1\n')
    _write(tmp_path / 'terr.csv', 'unit_id;built_up_proxy;forest_proxy;shrubland_proxy;wui_proxy;territorial_missing_flag\nU1;1;1;1;1;0\n')
    rows = step7.build_causal_matrix(tmp_path, 'NUTS3', tmp_path / 'smoke.csv', tmp_path / 'pop.csv', tmp_path / 'rec.csv', tmp_path / 'iech.csv', tmp_path / 'scen.csv', tmp_path / 'wrb.csv', tmp_path / 'terr.csv', tmp_path / 'out.csv')
    row = rows[0]
    assert row['population_smoke_day_burden_proxy_mean_2015_2024'] == 321
    assert row['population_smoke_day_burden_proxy_S0_mean_2026_2030'] == 400
    assert row['population_smoke_day_burden_proxy_S1_mean_2026_2030'] == 300
    assert row['delta_population_smoke_day_burden_proxy_S1_minus_S0'] == -100
