from pathlib import Path
import sys


def test_iech_historical_mean_uses_population_smoke_burden_proxy(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / 'pipeline' / 'RUN_QGIS' / 'STEP7_MATRIZ_CAUSAL'))
    import step7_matriz_causal as step7  # type: ignore

    pop = tmp_path / 'pop.csv'
    smoke = tmp_path / 'smoke.csv'
    hist = tmp_path / 'hist.csv'
    mean = tmp_path / 'mean.csv'
    pop.write_text('unit_id;pop_2015_sum;pop_2020_sum;pop_2025_sum;pop_2030_sum\nU1;10;10;10;10\n', encoding='utf-8')
    smoke.write_text('unit_id;year;smoke_days\n' + '\n'.join(f'U1;{y};2' for y in range(2015, 2025)) + '\n', encoding='utf-8')
    step7.compute_iech(pop, smoke, hist, mean)
    rows = step7.read_csv_rows(mean)[1]
    assert float(rows[0]['population_smoke_burden_proxy_mean_2015_2024']) == 480.0
    assert float(rows[0]['IECH_mean_2015_2024']) == 480.0