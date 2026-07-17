from pathlib import Path
import sys


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def test_modulec_runtime_scenario_mean_preserves_proxy_delta(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / 'pipeline'))
    import moduleC_pipeline_v2 as mod  # type: ignore

    tables = tmp_path / 'tables'
    qa = tmp_path / 'qa'
    qa.mkdir(parents=True)

    _write(
        tables / 'pop_unit_2015_2025_2030.csv',
        'unit_id;pop_2015_sum;pop_2020_sum;pop_2025_sum;pop_2030_sum;pop_missing_flag\n'
        'U1;100;100;100;100;0\n',
    )
    smoke_lines = ['unit_id;year;smoke_days']
    for year in range(2015, 2025):
        smoke_lines.append(f'U1;{year};50')
    _write(tables / 'smoke_days_unit_2015_2024.csv', '\n'.join(smoke_lines) + '\n')

    report = mod.Report(qa / 'report.txt')
    scen_csv, mean_csv = mod.scenarios_compute(tables, report)
    scen_rows = mod.read_csv_rows(scen_csv)[1]
    mean_rows = mod.read_csv_rows(mean_csv)[1]

    s0 = [float(r['population_smoke_burden_proxy']) for r in scen_rows if r['scenario'] == 'S0']
    s1 = [float(r['population_smoke_burden_proxy']) for r in scen_rows if r['scenario'] == 'S1']
    observed = mean_rows[0]
    assert float(observed['population_smoke_burden_proxy_S0_mean_2026_2030']) == sum(s0) / len(s0)
    assert float(observed['population_smoke_burden_proxy_S1_mean_2026_2030']) == sum(s1) / len(s1)
    assert float(observed['delta_population_smoke_burden_proxy_S1_minus_S0']) < 0
