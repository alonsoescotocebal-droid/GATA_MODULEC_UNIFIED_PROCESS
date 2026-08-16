import datetime as dt
import json
import sys
from pathlib import Path


def _load_pipeline_module():
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / 'pipeline'))
    import moduleC_pipeline_v2 as mod  # type: ignore

    return mod


def _seed_regressed_smoke_runtime(output_root: Path) -> None:
    qa_dir = output_root / 'qa'
    tables_dir = output_root / 'tables'
    brief_dir = output_root / 'brief' / 'causal_matrix'
    deliver_dir = output_root / 'deliverables_step9'
    qa_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)
    brief_dir.mkdir(parents=True, exist_ok=True)
    deliver_dir.mkdir(parents=True, exist_ok=True)

    (qa_dir / 'inputs_resolved.json').write_text(json.dumps({'meta': {}, 'paths': {}}, indent=2), encoding='utf-8')
    (output_root / 'brief' / 'Brief_Politica_IECH_2030.md').write_text('brief\n', encoding='utf-8')
    (brief_dir / 'causal_matrix_IECH_NUTS3.csv').write_text('unit_id;unit_name\nPT01;Unit 1\n', encoding='utf-8')

    (qa_dir / 'gfas_era5_decoder_daily_spatial_audit.tsv').write_text(
        'metric\tvalue\tstatus\tdetail\n'
        'daily_rows\t2418\tPASS\tseeded\n'
        'unique_dates\t93\tPASS\tseeded\n'
        'unique_years\t1\tPASS\tseeded\n'
        'unique_units\t26\tPASS\tseeded\n'
        'homogeneous_years\t0\tPASS\tseeded\n',
        encoding='utf-8',
    )
    route_lines = [
        'year\tunique_values\tmethod\tspatial_homogeneous_flag\troute_selected\tsmoke_route_status\tsmoke_route_decision\thealth_exposure_claim\tiech_decision\tcausal_matrix_decision\tbrief_decision\tfinal_scientific_decision'
    ]
    for year in range(2015, 2025):
        method = 'gfas_era5_proxy_p60_unit_daily_spatial_direct_year' if year == 2017 else 'gfas_era5_proxy_p60_unit_daily_spatial_flat_single_anchor'
        route_lines.append(
            f'{year}\t5\t{method}\t0\tv0_gfas_era5_advection_screening_proxy\tPASS\tTHRESHOLD_DEFINED_AS_INDEXED_METHOD\tBLOCKED\tPASS\tPASS\tPASS\tPASS'
        )
    (qa_dir / 'smoke_route_audit.tsv').write_text('\n'.join(route_lines) + '\n', encoding='utf-8')

    units = [f'PT{index:02d}' for index in range(1, 27)]
    daily_lines = [
        'unit_id;unit_name;unit_level;date;year;source_file;band_index;pm2p5fire_mean;pm2p5fire_max;pm2p5fire_sum;valid_pixel_count;smoke_day_score;threshold_id;threshold_value;smoke_day_proxy;smoke_day_equivalent;spatial_assignment_method;qa_flag'
    ]
    daily_dates = [dt.date(2017, 1, 1) + dt.timedelta(days=offset) for offset in range(93)]
    for date_value in daily_dates:
        for idx, unit_id in enumerate(units, start=1):
            daily_lines.append(
                f'{unit_id};Unit {idx};NUTS3;{date_value.isoformat()};{date_value.year};seed.grib;1;{idx};{idx};{idx};10;{idx};GFAS_ERA5_PROXY_SMOKE_DAY_P60;1;1;1;CENTROID_FALLBACK_LIMITED;0'
            )
    (tables_dir / 'smoke_day_score_nuts3_daily.csv').write_text('\n'.join(daily_lines) + '\n', encoding='utf-8')


def test_complete_post_smoke_runtime_blocks_portuguese_aq_after_base_smoke_regression(monkeypatch, tmp_path):
    mod = _load_pipeline_module()
    output_root = tmp_path / 'runtime'
    _seed_regressed_smoke_runtime(output_root)

    aq_calls = []
    blocked_calls = []
    manifest_outputs = []

    monkeypatch.setattr(mod, 'refresh_smoke_route_v0_audit', lambda _output_root: None)
    monkeypatch.setattr(mod, 'write_oc03_v11_decoder_contract_validation', lambda _output_root: None)
    monkeypatch.setattr(mod, 'run_step7_causal_extension', lambda _gata_root, _output_root, _report: None)
    monkeypatch.setattr(mod, 'run_objectives_gate', lambda _output_root, _report, mode='pre': None)

    def fake_scientific_gate(runtime_root, _report):
        scientific_path = runtime_root / 'deliverables_step9' / 'runtime_scientific_closure_decision.md'
        scientific_path.parent.mkdir(parents=True, exist_ok=True)
        scientific_path.write_text('blocked\n', encoding='utf-8')
        (runtime_root / 'deliverables_step9' / 'runtime_closure_decision.md').write_text('blocked\n', encoding='utf-8')
        return scientific_path

    monkeypatch.setattr(mod, 'run_scientific_gate', fake_scientific_gate)
    monkeypatch.setattr(mod, 'run_phase3_phase2_scientific_comparison', lambda _output_root, _report: None)
    monkeypatch.setattr(mod, 'run_global_audit_status_scan', lambda _output_root, _report: None)
    monkeypatch.setattr(mod, 'assert_global_audit_status_clear', lambda _output_root, _report: None)
    monkeypatch.setattr(mod, 'run_qa_gate', lambda _tables_dir, _brief_path, _report: ('GO', 'stubbed', []))

    def fake_build_manifest(outputs, _out_dir, _report):
        manifest_outputs.extend(path.as_posix() for path in outputs)
        deliver_dir = output_root / 'deliverables_step9'
        deliver_dir.mkdir(parents=True, exist_ok=True)
        (deliver_dir / 'final_manifest.json').write_text('[]', encoding='utf-8')
        (deliver_dir / 'final_manifest_recursive_audit.tsv').write_text(
            'relative_path\tbytes\tsha256\n', encoding='utf-8'
        )
        (deliver_dir / 'final_sha256_checkpoints.txt').write_text(
            'STEP9_FINAL_MASTER_PACK checkpoint\n', encoding='utf-8'
        )
        return output_root / 'deliverables_step9' / 'final_manifest.json', output_root / 'deliverables_step9' / 'final_sha256_checkpoints.txt', output_root / 'deliverables_step9' / 'ModuleC_ALL_FINAL_deliverables.zip'

    monkeypatch.setattr(mod, 'build_manifest_and_zip', fake_build_manifest)

    def fake_run_portuguese_aq_validation(**kwargs):
        aq_calls.append(kwargs)
        raise AssertionError('Portuguese AQ validation must not run after a regressed base smoke contract.')

    monkeypatch.setattr(mod, 'run_portuguese_aq_validation', fake_run_portuguese_aq_validation)

    def fake_blocked_base_smoke_outputs(modulec_datos, output_root, repo_root, report_log=None):
        blocked_calls.append((modulec_datos, output_root, repo_root))
        qa_dir = output_root / 'qa'
        qa_dir.mkdir(parents=True, exist_ok=True)
        (qa_dir / 'portuguese_aq_validation_gate.tsv').write_text(
            'metric\tvalue\tstatus\tdetail\n'
            'portuguese_aq_validation_status\tBLOCKED_BASE_SMOKE_REGRESSION\tPASS\tblocked\n'
            'final_proxy_tier\tTIER_3_PEER_REVIEWED_OPERATIONAL_PROXY\tPASS\tblocked\n'
            'aq_protocol_decision\tBLOCKED_BASE_SMOKE_REGRESSION\tPASS\tblocked\n'
            'claim_disposition\tBLOCKED_BASE_SMOKE_REGRESSION\tPASS\tblocked\n'
            'health_exposure_claim_status\tHEALTH_EXPOSURE_CLAIM_BLOCKED\tPASS\tblocked\n',
            encoding='utf-8',
        )
        return {
            'portuguese_aq_root': '',
            'portuguese_aq_validation_status': 'BLOCKED_BASE_SMOKE_REGRESSION',
            'final_proxy_tier': 'TIER_3_PEER_REVIEWED_OPERATIONAL_PROXY',
            'aq_protocol_decision': 'BLOCKED_BASE_SMOKE_REGRESSION',
            'claim_disposition': 'BLOCKED_BASE_SMOKE_REGRESSION',
            'health_exposure_claim_status': 'HEALTH_EXPOSURE_CLAIM_BLOCKED',
        }

    monkeypatch.setattr(mod, 'write_blocked_base_smoke_regression_outputs', fake_blocked_base_smoke_outputs)

    report = mod.Report(output_root / 'qa' / 'run_log.txt')
    mod.complete_post_smoke_runtime(
        gata_root=tmp_path / 'repo',
        modulec_datos=tmp_path / 'repo' / 'Module C' / 'Datos',
        output_root=output_root,
        report=report,
        rerun_step7=False,
    )

    assert aq_calls == []
    assert len(blocked_calls) == 1
    gate_text = (output_root / 'qa' / 'oc03c_base_smoke_contract_gate.tsv').read_text(encoding='utf-8')
    alias_text = (output_root / 'qa' / 'oc03_base_smoke_contract_gate.tsv').read_text(encoding='utf-8')
    aq_gate_text = (output_root / 'qa' / 'portuguese_aq_validation_gate.tsv').read_text(encoding='utf-8')
    inputs_payload = json.loads((output_root / 'qa' / 'inputs_resolved.json').read_text(encoding='utf-8'))

    assert 'BLOCKED_BASE_SMOKE_REGRESSION' in gate_text
    assert alias_text == gate_text
    assert 'BLOCKED_BASE_SMOKE_REGRESSION' in aq_gate_text
    assert inputs_payload['meta']['base_smoke_contract_for_oc03c_status'] == 'BLOCKED_BASE_SMOKE_REGRESSION'
    assert inputs_payload['meta']['portuguese_aq_validation_status'] == 'BLOCKED_BASE_SMOKE_REGRESSION'
    assert (output_root / 'qa' / 'oc03_base_smoke_contract_report.md').exists()
    assert any(path.endswith('qa/oc03_base_smoke_contract_gate.tsv') for path in manifest_outputs)
