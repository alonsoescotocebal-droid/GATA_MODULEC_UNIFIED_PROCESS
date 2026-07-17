from pathlib import Path
import sys


def test_iech_scenario_mean_preserves_s1_delta(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / 'pipeline' / 'RUN_QGIS' / 'STEP7_MATRIZ_CAUSAL'))
    import step7_matriz_causal as step7  # type: ignore

    pop = tmp_path / 'pop.csv'
    smoke = tmp_path / 'smoke.csv'
    scen = tmp_path / 'scen.csv'
    mean = tmp_path / 'mean.csv'
    pop.write_text('unit_id;pop_2025_sum;pop_2030_sum\nU1;10;10\n', encoding='utf-8')
    smoke.write_text('unit_id;year;smoke_days\n' + '\n'.join(f'U1;{y};5' for y in range(2015, 2025)) + '\n', encoding='utf-8')
    step7.compute_scenarios(smoke, pop, scen, mean)
    rows = step7.read_csv_rows(mean)[1]
    assert float(rows[0]['population_smoke_burden_proxy_S0_mean_2026_2030']) == 1200.0
    assert float(rows[0]['population_smoke_burden_proxy_S1_mean_2026_2030']) == 960.0
    assert float(rows[0]['delta_population_smoke_burden_proxy_S1_minus_S0']) == -240.0