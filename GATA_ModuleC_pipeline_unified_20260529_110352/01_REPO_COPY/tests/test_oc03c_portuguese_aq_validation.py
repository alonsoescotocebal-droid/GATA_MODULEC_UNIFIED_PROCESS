from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path


def _load_aq_module():
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import portuguese_aq_validation as mod  # type: ignore

    return mod


def _load_pipeline_module():
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import moduleC_pipeline_v2 as mod  # type: ignore

    return mod


def _load_validator_module():
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import validate_modulec_objectives_canon as mod  # type: ignore

    return mod


def _load_qa_gate_module():
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import qa_gate_v2 as mod  # type: ignore

    return mod


def _write_minimal_qualar_xlsx(path: Path) -> None:
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>
"""
    root_rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
"""
    workbook = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Sheet1" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>
"""
    workbook_rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>
"""
    sheet = """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1">
      <c r="A1" t="inlineStr"><is><t>PM10 (µg/m3)</t></is></c>
      <c r="B1" t="inlineStr"><is><t>Lisboa</t></is></c>
    </row>
    <row r="2">
      <c r="A2" t="inlineStr"><is><t>2019-08-01 00:00:00</t></is></c>
      <c r="B2"><v>25</v></c>
    </row>
    <row r="3">
      <c r="A3" t="inlineStr"><is><t>2019-08-01 01:00:00</t></is></c>
      <c r="B3"><v>35</v></c>
    </row>
  </sheetData>
</worksheet>
"""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        zf.writestr("xl/worksheets/sheet1.xml", sheet)


def _seed_minimal_runtime(output_root: Path, oc03c_status: str = "PORTUGUESE_AQ_CONCORDANCE_INSUFFICIENT") -> None:
    qa_dir = output_root / "qa"
    tables_dir = output_root / "tables"
    brief_dir = output_root / "brief" / "causal_matrix"
    deliver_dir = output_root / "deliverables_step9"
    qa_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)
    brief_dir.mkdir(parents=True, exist_ok=True)
    deliver_dir.mkdir(parents=True, exist_ok=True)

    (tables_dir / "IECH_unit_2015_2024.csv").write_text("unit_id;IECH;smoke_hours_equiv\nA;2;1\n", encoding="utf-8")
    (tables_dir / "smoke_days_unit_2015_2024.csv").write_text("unit_id;year;smoke_days\nA;2020;2\nB;2020;4\n", encoding="utf-8")
    (tables_dir / "pop_unit_2015_2025_2030.csv").write_text("unit_id;pop_2020_sum\nA;10\n", encoding="utf-8")
    (tables_dir / "recurrence_unit_2015_2024.csv").write_text("unit_id;recurrence\nA;1\n", encoding="utf-8")
    (tables_dir / "IECH_municipio_2015_2024.csv").write_text("municipio_id;IECH\nA;2\n", encoding="utf-8")
    (tables_dir / "wrb_context_nuts3.csv").write_text("unit_id;wrb_missing_flag\nA;0\n", encoding="utf-8")
    (tables_dir / "territorial_context_nuts3.csv").write_text("unit_id;wui_proxy\nA;1\n", encoding="utf-8")

    (brief_dir / "causal_matrix_IECH_NUTS3.csv").write_text("unit_id;missing_components;qa_flag\nA;;PASS\n", encoding="utf-8")
    (brief_dir / "causal_matrix_IECH_NUTS3.json").write_text("{}", encoding="utf-8")
    (output_root / "brief" / "Brief_Politica_IECH_2030.md").write_text("A" * 1400, encoding="utf-8")

    (qa_dir / "objectives_canon_alignment_report.tsv").write_text(
        "objective_id\tobjective_name\trequired_database\trequired_output\tproducer_script\tvalidation_rule\tstatus\tevidence_path\tfailure_reason\n"
        "OC-03C\tPortuguese AQ\tAQ root\tqa/portuguese_aq_validation_gate.tsv\tvalidator\trule\tPASS\t.\tValidated.\n",
        encoding="utf-8",
    )
    (qa_dir / "inputs_resolved.json").write_text(
        '{"meta":{"objectives_canon_path":"canon.md","objectives_canon_sha256":"abc","smoke_route_selected":"v0_gfas_era5_real","smoke_route_decision":"THRESHOLD_DEFINED_AS_INDEXED_METHOD"}}',
        encoding="utf-8",
    )
    (qa_dir / "scientific_validation_gate.tsv").write_text(
        "threshold_id\tcomponent\tinput_file_checked\tvariable_checked\tobserved_condition\tthreshold_value_or_rule\tthreshold_source_id\tsource_type\tgate_status\tallowed_claim\tforbidden_claim\tfinal_decision_effect\n"
        "OC03C-AQ-001\tPortuguese AQ\tqa/portuguese_aq_validation_gate.tsv\tstatus\tok\trule\tsrc\tLOCAL_VALIDATION_GATE\tTHRESHOLD_DEFINED_AS_INDEXED_METHOD\tallowed\tforbidden\tNONE\n",
        encoding="utf-8",
    )

    for rel in [
        "qa/portuguese_aq_input_inventory.tsv",
        "qa/portuguese_aq_file_format_audit.tsv",
        "qa/portuguese_aq_station_inventory.tsv",
        "qa/portuguese_aq_timeseries_inventory.tsv",
        "qa/portuguese_aq_normalization_audit.tsv",
        "qa/portuguese_aq_station_to_unit_assignment.tsv",
        "qa/gfas_era5_vs_portuguese_aq_concordance.tsv",
        "qa/portuguese_aq_claim_disposition.md",
        "tables/portuguese_aq_daily_station_2015_2024.csv",
        "tables/portuguese_aq_daily_unit_2015_2024.csv",
        "tables/smoke_proxy_aq_concordance_by_unit.csv",
    ]:
        path = output_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("stub\n", encoding="utf-8")

    (qa_dir / "oc03c_path_scope_preflight.tsv").write_text(
        "timestamp\tcheck_id\tstatus\tobserved\texpected\tdetail\n"
        "2026-01-01T00:00:00\tOC03C_SUMMARY\tPATH_SCOPE_PASS\tPATH_SCOPE_PASS\tPATH_SCOPE_PASS\tAll checks passed.\n",
        encoding="utf-8",
    )

    claim_disposition = "PORTUGUESE_AQ_VALIDATION_NOT_CONSUMED_OR_INSUFFICIENT"
    protocol = "GO_DIRECT_2015_2024_FOR_PROSPECTIVE_PROXY_SCREENING"
    health_status = "HEALTH_EXPOSURE_CLAIM_BLOCKED"
    if oc03c_status == "LOCAL_AQ_ANCHORED_PROXY":
        claim_disposition = "GFAS/ERA5 smoke proxy is locally supported by Portuguese/EEA air-quality observations"
        protocol = "GO_WITH_PORTUGUESE_AQ_ANCHORED_PROXY_PROTOCOL"
        health_status = "HEALTH_EXPOSURE_NOT_DECLARED"
        (qa_dir / "gfas_era5_vs_portuguese_aq_concordance.tsv").write_text(
            "pollutant\tscope\tmatched_day_count\thigh_gfas_day_count\tnon_high_day_count\tmedian_pollutant_on_high_days\tmedian_pollutant_on_non_high_days\tdelta_median\tspearman_correlation\tsame_day_coincidence_count\tplusminus1_coincidence_count\tstation_count\tunit_count\tconcordance_signal\n"
            "PM10\tSPATIAL_MATCHED\t4\t2\t2\t30\t10\t20\t0.8\t2\t3\t1\t1\tPOSITIVE\n",
            encoding="utf-8",
        )

    (qa_dir / "portuguese_aq_validation_gate.tsv").write_text(
        "metric\tvalue\tstatus\tdetail\n"
        f"portuguese_aq_validation_status\t{oc03c_status}\tPASS\tOC-03C outcome\n"
        "final_proxy_tier\tTIER_3_PEER_REVIEWED_OPERATIONAL_PROXY\tPASS\tProxy tier\n"
        f"aq_protocol_decision\t{protocol}\tPASS\tProtocol\n"
        f"claim_disposition\t{claim_disposition}\tPASS\tClaim\n"
        f"health_exposure_claim_status\t{health_status}\tPASS\tHealth status\n",
        encoding="utf-8",
    )


def test_normalize_pollutant_name_maps_known_aliases():
    mod = _load_aq_module()

    assert mod.normalize_pollutant_name("pm2_5 ug m3") == "PM2.5"
    assert mod.normalize_pollutant_name("sulphur dioxide") == "SO2"


def test_resolve_portuguese_aq_root_requires_exact_approved_folder_name(tmp_path):
    mod = _load_aq_module()
    modulec_datos = tmp_path / "Datos"
    modulec_datos.mkdir()
    wrong = tmp_path / "Datos_RECOVERY_PORTUGUESE_AGENCIES_2015_2024_COPY"
    wrong.mkdir()

    assert mod.resolve_portuguese_aq_root(modulec_datos) is None

    approved = tmp_path / "Datos_RECOVERY_PORTUGUESE_AGENCIES_2015_2024"
    approved.mkdir()
    assert mod.resolve_portuguese_aq_root(modulec_datos) == approved


def test_parse_qualar_xlsx_reads_wide_matrix_without_openpyxl(tmp_path):
    mod = _load_aq_module()
    xlsx_path = tmp_path / "QUALAR_PM10.xlsx"
    _write_minimal_qualar_xlsx(xlsx_path)

    meta, observations, stations = mod.parse_qualar_xlsx(xlsx_path)

    assert meta["status"] == "PASS"
    assert meta["pollutant"] == "PM10"
    assert meta["unit"] == "µg/m3"
    assert meta["station_count"] == 1
    assert len(observations) == 2
    assert len(stations) == 1
    assert observations[0]["date"] == "2019-08-01"


def test_determine_gate_keeps_proxy_tier_when_aq_inventory_missing():
    mod = _load_aq_module()

    gate = mod.determine_gate(
        discovered_files=0,
        timeseries_files_normalized=0,
        daily_station_count=0,
        assigned_station_count=0,
        concordance_rows=[],
        threshold_comparisons_present=False,
    )

    assert gate["portuguese_aq_validation_status"] == "NO_PORTUGUESE_AQ_DATA_FOUND"
    assert gate["final_proxy_tier"] == "TIER_3_PEER_REVIEWED_OPERATIONAL_PROXY"
    assert gate["aq_protocol_decision"] == "GO_DIRECT_2015_2024_FOR_PROSPECTIVE_PROXY_SCREENING"
    assert gate["health_exposure_claim_status"] == "HEALTH_EXPOSURE_CLAIM_BLOCKED"


def test_determine_gate_positive_concordance_only_reaches_local_anchored_proxy_without_thresholds():
    mod = _load_aq_module()

    gate = mod.determine_gate(
        discovered_files=10,
        timeseries_files_normalized=2,
        daily_station_count=5,
        assigned_station_count=2,
        concordance_rows=[
            {
                "scope": "SPATIAL_MATCHED",
                "concordance_signal": "POSITIVE",
                "matched_day_count": 4,
                "high_gfas_day_count": 2,
            }
        ],
        threshold_comparisons_present=False,
    )

    assert gate["portuguese_aq_validation_status"] == "LOCAL_AQ_ANCHORED_PROXY"
    assert gate["aq_protocol_decision"] == "GO_WITH_PORTUGUESE_AQ_ANCHORED_PROXY_PROTOCOL"
    assert gate["health_exposure_claim_status"] == "HEALTH_EXPOSURE_NOT_DECLARED"


def test_collect_final_outputs_includes_oc03c_artifacts(tmp_path):
    mod = _load_pipeline_module()
    output_root = tmp_path / "runtime"
    scientific_decision = output_root / "deliverables_step9" / "runtime_scientific_closure_decision.md"

    outputs = {path.as_posix() for path in mod.collect_final_outputs(output_root, scientific_decision)}

    assert (output_root / "qa" / "oc03c_path_scope_preflight.tsv").as_posix() in outputs
    assert (output_root / "qa" / "portuguese_aq_validation_gate.tsv").as_posix() in outputs
    assert (output_root / "tables" / "portuguese_aq_daily_unit_2015_2024.csv").as_posix() in outputs


def test_oc03c_objective_check_accepts_insufficient_aq_without_upgrading(tmp_path):
    mod = _load_validator_module()
    output_root = tmp_path / "runtime"
    _seed_minimal_runtime(output_root, oc03c_status="PORTUGUESE_AQ_CONCORDANCE_INSUFFICIENT")

    ok, reason = mod._check_oc03c_aq_validation(output_root)

    assert ok is True
    assert "without local upgrade" in reason


def test_oc03c_objective_check_requires_positive_concordance_for_anchored_upgrade(tmp_path):
    mod = _load_validator_module()
    output_root = tmp_path / "runtime"
    _seed_minimal_runtime(output_root, oc03c_status="LOCAL_AQ_ANCHORED_PROXY")
    (output_root / "qa" / "gfas_era5_vs_portuguese_aq_concordance.tsv").write_text(
        "pollutant\tscope\tconcordance_signal\nPM10\tSPATIAL_MATCHED\tNEGATIVE\n",
        encoding="utf-8",
    )

    ok, reason = mod._check_oc03c_aq_validation(output_root)

    assert ok is False
    assert "positive spatial concordance" in reason


def test_qa_gate_holds_when_oc03c_artifacts_missing(tmp_path):
    mod = _load_qa_gate_module()
    output_root = tmp_path / "runtime"
    _seed_minimal_runtime(output_root)
    (output_root / "qa" / "portuguese_aq_validation_gate.tsv").unlink()

    decision, _summary, holds, _rows = mod.evaluate_output_root(output_root)

    assert decision == "HOLD"
    assert "HOLD OC-03C AQ VALIDATION" in holds


def test_qa_gate_does_not_hold_on_oc03c_insufficient_status_when_artifacts_exist(tmp_path):
    mod = _load_qa_gate_module()
    output_root = tmp_path / "runtime"
    _seed_minimal_runtime(output_root, oc03c_status="PORTUGUESE_AQ_CONCORDANCE_INSUFFICIENT")

    decision, _summary, holds, _rows = mod.evaluate_output_root(output_root)

    assert "HOLD OC-03C AQ VALIDATION" not in holds
    assert decision == "GO"



def _write_qualar_xlsx_rows(path: Path, rows: list[tuple[str, float]], station_name: str = "Lisboa") -> None:
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>
"""
    root_rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
"""
    workbook = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Sheet1" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>
"""
    workbook_rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>
"""
    row_xml = [
        '    <row r="1">',
        '      <c r="A1" t="inlineStr"><is><t>PM10 (?/m3)</t></is></c>',
        f'      <c r="B1" t="inlineStr"><is><t>{station_name}</t></is></c>',
        '    </row>',
    ]
    for idx, (dt_text, value) in enumerate(rows, start=2):
        row_xml.extend(
            [
                f'    <row r="{idx}">',
                f'      <c r="A{idx}" t="inlineStr"><is><t>{dt_text}</t></is></c>',
                f'      <c r="B{idx}"><v>{value}</v></c>',
                '    </row>',
            ]
        )
    sheet = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">\n'
        '  <sheetData>\n'
        + "\n".join(row_xml)
        + '\n  </sheetData>\n'
        '</worksheet>\n'
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        zf.writestr("xl/worksheets/sheet1.xml", sheet)



def _prepare_oc03c_runner_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    repo_root = tmp_path / "sandbox" / "01_REPO_COPY"
    output_root = tmp_path / "sandbox" / "03_RUNTIMES" / "runtime_001"
    data_parent = tmp_path / "data"
    modulec_datos = data_parent / "Datos"
    aq_root = data_parent / "Datos_RECOVERY_PORTUGUESE_AGENCIES_2015_2024"

    (repo_root / "config").mkdir(parents=True, exist_ok=True)
    modulec_datos.mkdir(parents=True, exist_ok=True)
    aq_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)

    config = {
        "DATA_ROOT_ALLOWED_PREFIX": str(modulec_datos),
        "DATA_ROOT_ALLOWED_PREFIXES": [
            str(modulec_datos),
            str(data_parent / "Datos_RECOVERY_2015_2024_PIPELINE_GRIB"),
            str(aq_root),
            str(data_parent / "Datos_RECOVERY_2015_2024"),
        ],
        "OUTPUT_ROOT_ALLOWED_PREFIX": str(output_root.parents[1]),
    }
    (repo_root / "config" / "module_c_canonical_paths.json").write_text(json.dumps(config, indent=2), encoding="utf-8")

    qa_dir = output_root / "qa"
    tables_dir = output_root / "tables"
    brief_dir = output_root / "brief" / "causal_matrix"
    qa_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)
    brief_dir.mkdir(parents=True, exist_ok=True)

    (qa_dir / "inputs_resolved.json").write_text('{"meta":{},"paths":{}}', encoding="utf-8")
    (tables_dir / "municipio_unit_map.csv").write_text(
        "municipio_id;nuts3_id;mapping_ok\nLisboa;PT17;1\n",
        encoding="utf-8",
    )
    (brief_dir / "causal_matrix_IECH_NUTS3.csv").write_text(
        "unit_id;unit_name\nPT17;Lisboa\n",
        encoding="utf-8",
    )

    smoke_rows = ["unit_id;date;smoke_day_score;smoke_day_proxy"]
    for day in range(1, 11):
        date_value = f"2019-08-{day:02d}"
        high = 1 if day <= 4 else 0
        smoke_rows.append(f"Lisboa;{date_value};{high};{high}")
    (tables_dir / "smoke_day_score_municipio_daily.csv").write_text("\n".join(smoke_rows) + "\n", encoding="utf-8")
    (tables_dir / "smoke_day_score_nuts3_daily.csv").write_text(
        "unit_id;date;smoke_day_score;smoke_day_proxy\n",
        encoding="utf-8",
    )
    return repo_root, modulec_datos, aq_root, output_root



def test_run_portuguese_aq_validation_from_approved_root_produces_anchored_proxy(monkeypatch, tmp_path):
    mod = _load_aq_module()
    repo_root, modulec_datos, aq_root, output_root = _prepare_oc03c_runner_fixture(tmp_path)
    monkeypatch.chdir(repo_root)

    manual_dir = aq_root / "01_APA_QUALAR" / "manual_exports"
    manual_dir.mkdir(parents=True, exist_ok=True)
    xlsx_path = manual_dir / "QUALAR_PM10_ALL_STATIONS_2019-08-01_2019-08-10.xlsx"
    rows = []
    for day in range(1, 11):
        value = 40.0 if day <= 4 else 5.0
        rows.append((f"2019-08-{day:02d} 00:00:00", value))
    _write_qualar_xlsx_rows(xlsx_path, rows)

    result = mod.run_portuguese_aq_validation(modulec_datos=modulec_datos, output_root=output_root, repo_root=repo_root)

    assert result["portuguese_aq_root"] == str(aq_root)
    assert result["portuguese_aq_files_discovered"] == 1
    assert result["portuguese_aq_timeseries_files_normalized"] == 1
    assert result["portuguese_aq_validation_status"] == "LOCAL_AQ_ANCHORED_PROXY"
    assert result["aq_protocol_decision"] == "GO_WITH_PORTUGUESE_AQ_ANCHORED_PROXY_PROTOCOL"
    assert result["health_exposure_claim_status"] == "HEALTH_EXPOSURE_NOT_DECLARED"
    assert result["portuguese_aq_path_scope_decision"] == "PATH_SCOPE_PASS"
    assert (output_root / "qa" / "portuguese_aq_validation_gate.tsv").exists()
    assert (output_root / "tables" / "portuguese_aq_daily_unit_2015_2024.csv").exists()



def test_run_portuguese_aq_validation_rejects_out_of_scope_env_root_before_inventory(monkeypatch, tmp_path):
    mod = _load_aq_module()
    repo_root, modulec_datos, _aq_root, output_root = _prepare_oc03c_runner_fixture(tmp_path)
    monkeypatch.chdir(repo_root)

    rogue_root = tmp_path / "rogue" / "Datos_RECOVERY_PORTUGUESE_AGENCIES_2015_2024"
    manual_dir = rogue_root / "01_APA_QUALAR" / "manual_exports"
    manual_dir.mkdir(parents=True, exist_ok=True)
    _write_qualar_xlsx_rows(manual_dir / "QUALAR_PM10_ROGUE.xlsx", [("2019-08-01 00:00:00", 99.0)])
    monkeypatch.setenv("MODULEC_OC03_PORTUGUESE_AQ_ROOT", str(rogue_root))

    result = mod.run_portuguese_aq_validation(modulec_datos=modulec_datos, output_root=output_root, repo_root=repo_root)

    assert result["portuguese_aq_root"] == str(rogue_root)
    assert result["portuguese_aq_files_discovered"] == 0
    assert result["portuguese_aq_validation_status"] == "NO_PORTUGUESE_AQ_DATA_FOUND"
    assert result["portuguese_aq_path_scope_decision"] == "BLOCKED_PATH_SCOPE_DESYNC"
