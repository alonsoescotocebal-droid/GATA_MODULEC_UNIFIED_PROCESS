from pathlib import Path
import sys


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def test_modulec_runtime_unit_mean_uses_population_smoke_burden_proxy(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / 'pipeline'))
    import moduleC_pipeline_v2 as mod  # type: ignore

    tables = tmp_path / 'tables'
    qa = tmp_path / 'qa'
    qa.mkdir(parents=True)

    _write(
        tables / 'pop_unit_2015_2025_2030.csv',
        'unit_id;pop_2015_sum;pop_2020_sum;pop_2025_sum;pop_2030_sum;pop_missing_flag\n'
        'U1;100;200;300;400;0\n',
    )
    smoke_lines = ['unit_id;year;smoke_days']
    for year, smoke_days in zip(range(2015, 2025), [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]):
        smoke_lines.append(f'U1;{year};{smoke_days}')
    _write(tables / 'smoke_days_unit_2015_2024.csv', '\n'.join(smoke_lines) + '\n')
    _write(tables / 'recurrence_unit_2015_2024.csv', 'unit_id;dummy\nU1;0\n')

    report = mod.Report(qa / 'report.txt')
    hist_csv, mean_csv = mod.iech_compute(tables, report)
    hist_rows = mod.read_csv_rows(hist_csv)[1]
    mean_rows = mod.read_csv_rows(mean_csv)[1]

    expected = sum(float(r['population_smoke_burden_proxy']) for r in hist_rows) / len(hist_rows)
    observed = float(mean_rows[0]['population_smoke_burden_proxy_mean_2015_2024'])
    assert observed == expected
    assert observed != float(mean_rows[0]['unit_id'] == 'U1')
