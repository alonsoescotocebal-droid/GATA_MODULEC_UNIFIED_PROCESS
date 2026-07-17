from pathlib import Path
import sys


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def test_brief_uses_repaired_proxy_and_scenario_means(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / 'pipeline' / 'RUN_QGIS' / 'STEP7_MATRIZ_CAUSAL'))
    import step7_matriz_causal as step7  # type: ignore

    out = tmp_path
    tables = out / 'tables'
    brief = out / 'brief' / 'causal_matrix'
    _write(tables / 'smoke_days_unit_2015_2024.csv', 'unit_id;year;smoke_days\nU1;2015;1\n')
    _write(tables / 'pop_unit_2015_2025_2030.csv', 'unit_id;pop_2020_sum;pop_2030_sum\nU1;10;10\n')
    _write(tables / 'recurrence_unit_2015_2024.csv', 'unit_id;total_burn_ha_2015_2024;years_area_gt_p75;n_events_gt_1000ha;recurrence_class\nU1;0;0;0;LOW\n')
    _write(tables / 'IECH_unit_2015_2024.csv', 'unit_id;population_smoke_burden_proxy\nU1;100\n')
    _write(tables / 'IECH_unit_2015_2024_mean.csv', 'unit_id;population_smoke_burden_proxy_mean_2015_2024;IECH_mean_2015_2024\nU1;321;321\n')
    _write(tables / 'IECH_scenarios_2026_2030.csv', 'unit_id;year;scenario;IECH;delta_vs_S0\nU1;2026;S0;400;0\nU1;2026;S1;300;-100\n')
    _write(tables / 'IECH_scenarios_unit_2026_2030_mean.csv', 'unit_id;population_smoke_burden_proxy_S0_mean_2026_2030;population_smoke_burden_proxy_S1_mean_2026_2030;delta_population_smoke_burden_proxy_S1_minus_S0;IECH_S0_mean_2026_2030;IECH_S1_mean_2026_2030;delta_S1_minus_S0\nU1;400;300;-100;400;300;-100\n')
    _write(tables / 'IECH_municipio_2015_2024.csv', 'unit_id;population_smoke_burden_proxy\nU1;100\n')
    _write(tables / 'wrb_context_nuts3.csv', 'unit_id;dominant_wrb_class\nU1;\n')
    _write(tables / 'territorial_context_nuts3.csv', 'unit_id;wui_proxy\nU1;1\n')
    _write(brief / 'causal_matrix_IECH_NUTS3.csv', 'unit_id;qa_flag;missing_components\nU1;OK;\n')
    inputs = {'paths': {'nuts3': 'n', 'municipios_caop': 'm', 'ghsl_pop': {}, 'fire_gpkgs_tm06': []}, 'meta': {}}
    brief_path = step7.generate_brief(out, inputs)
    text = brief_path.read_text(encoding='utf-8')
    assert 'min=321.0 max=321.0' in text
    assert 'Delta medio S1-S0 (NUTS3 mean): -100.0.' in text