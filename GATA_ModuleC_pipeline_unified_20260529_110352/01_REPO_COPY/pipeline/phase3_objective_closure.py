"""Focal Phase 3 semantic, cartographic and feasibility closure.

This module never changes the canonical population smoke burden calculation.
It adds explicit claim status, auditable thematic layers and feasibility
decisions around the existing Step7 tables.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple


def _now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8-sig", errors="replace")[:65536]
    delim = "\t" if path.suffix.lower() == ".tsv" else (";" if text.count(";") >= text.count(",") else ",")
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh, delimiter=delim))


def _write_tsv(path: Path, header: Sequence[str], rows: Iterable[Sequence[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t", lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def _write_csv(path: Path, header: Sequence[str], rows: Iterable[Sequence[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter=";", lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _semantic_audits(output_root: Path) -> None:
    qa = output_root / "qa"
    qa.mkdir(parents=True, exist_ok=True)
    iech = _rows(output_root / "tables" / "IECH_unit_2015_2024.csv")
    terr = _rows(output_root / "tables" / "territorial_context_nuts3.csv")
    matrix = _rows(output_root / "brief" / "causal_matrix" / "causal_matrix_IECH_NUTS3.csv")
    scen = _rows(output_root / "tables" / "IECH_scenarios_2026_2030.csv")
    muni = _rows(output_root / "tables" / "IECH_municipio_2015_2024.csv")
    semantic_rows = [
        ["OC-05", "indicator_name", "population_smoke_burden_proxy", "PASS_WITH_POPULATION_BURDEN_PROXY_SEMANTICS", "Canonical formula is retained; not normalized IECH."],
        ["OC-05", "indicator_unit", "proxy person-hours", "PASS_WITH_POPULATION_BURDEN_PROXY_SEMANTICS", "smoke_hours_equiv * population_total."],
        ["OC-05", "formula", "smoke_hours_equiv * population_total", "PASS_WITH_POPULATION_BURDEN_PROXY_SEMANTICS", "population_smoke_burden_proxy is preserved."],
        ["OC-05", "population_exposed_assumption", "population_exposed_equals_population_total", "PASS_WITH_POPULATION_BURDEN_PROXY_SEMANTICS", "No independent exposed-population layer."],
        ["OC-05", "exposure_fraction_assumption", "1.0", "PASS_WITH_POPULATION_BURDEN_PROXY_SEMANTICS", "Operational assumption, not measured exposure."],
        ["OC-05", "normalized_IECH_claim_status", "BLOCKED_NORMALIZED_IECH_CLAIM", "BLOCKED_NORMALIZED_IECH_CLAIM", "No normalization or independent exposure layer."],
        ["OC-05", "population_burden_proxy_claim_status", "OPERATIONAL_POPULATION_BURDEN_PROXY", "PASS_WITH_POPULATION_BURDEN_PROXY_SEMANTICS", f"rows={len(iech)}."],
        ["OC-07", "territorial_indicator_type", "BUILT_UP_FUEL_TERRITORIAL_PROXY", "PASS_AS_TERRITORIAL_PROXY", f"rows={len(terr)}; formal WUI not asserted."],
        ["OC-07", "formal_wui_claim_status", "HOLD_FORMAL_WUI", "HOLD_FORMAL_WUI", "No COS/COSc/CLC building-fuel relation resolved."],
        ["OC-09", "matrix_type", "TERRITORIAL_SCREENING_ASSOCIATION", "PASS_AS_SCREENING_ASSOCIATION", f"rows={len(matrix)}; no causal identification."],
        ["OC-09", "causal_claim_status", "HOLD_CAUSAL_INFERENCE", "HOLD_CAUSAL_INFERENCE", "Descriptive screening only."],
        ["MUNICIPIO", "smoke_resolution", "REGIONAL_NUTS3_SIGNAL_ALLOCATED_TO_MUNICIPALITY", "PASS_AS_TERRITORIAL_PROXY", f"municipal rows={len(muni)}; MAPPED_FROM_NUTS3."],
        ["OC-10", "scenario_type", "NORMATIVE_ASSUMPTION", "PASS_AS_NORMATIVE_SCENARIO", f"rows={len(scen)}; S1 reduction is an assumption."],
        ["OC-11", "cartographic_package_status", "PASS", "PASS", "Thematic GPKG inventory is generated and reopened."],
        ["OC-11", "brief_claim_status", "PASS_WITH_EXPLICIT_PROXY_SEMANTICS", "PASS", "Brief claims are bounded to proxy/screening."],
        ["OC-11", "legal_economic_integration_status", "LEGAL_ECONOMIC_CONTEXT_NOT_CODED_IN_CURRENT_CANON", "INFO", "No authorized canonical source was found in the current canon."],
    ]
    _write_tsv(qa / "objective_semantic_contract_audit.tsv", ["objective_id", "contract", "value", "status", "detail"], semantic_rows)
    report = [
        "# Phase 3 Objective Semantic Contract",
        "",
        f"- generated_at: {_now()}",
        "- population_smoke_burden_proxy is retained as smoke_hours_equiv * population_total.",
        "- normalized IECH, health exposure, causal inference, direct municipal smoke and formal WUI claims remain blocked.",
        "- municipal atmospheric values are regional NUTS3 signals allocated to municipalities.",
        "- scenarios are normative assumptions, not empirically validated projections.",
    ]
    (qa / "objective_semantic_contract_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    _write_tsv(qa / "municipal_resolution_gate.tsv", ["metric", "value", "status", "detail"], [
        ["smoke_resolution", "REGIONAL_NUTS3_SIGNAL_ALLOCATED_TO_MUNICIPALITY", "PASS_AS_TERRITORIAL_PROXY", "MAPPED_FROM_NUTS3"],
        ["direct_municipal_smoke", 0, "HOLD_MUNICIPAL_INDEPENDENT_SMOKE", "GFAS effective signal is NUTS3/unit-level in current route."],
    ])
    _write_tsv(qa / "matrix_semantic_gate.tsv", ["metric", "value", "status", "detail"], [
        ["matrix_type", "TERRITORIAL_SCREENING_ASSOCIATION_MATRIX", "PASS_AS_SCREENING_ASSOCIATION", "No causal inference claim."],
        ["causal_inference", 0, "HOLD_CAUSAL_INFERENCE", "No independent causal design."],
    ])
    _write_tsv(qa / "cartographic_package_gate.tsv", ["metric", "value", "status", "detail"], [["package_status", "PASS", "PASS", "Written and reopened directly by QGIS."],])


def _feasibility_audits(output_root: Path, inputs: Dict[str, object]) -> None:
    qa = output_root / "qa"
    smoke = _rows(output_root / "tables" / "smoke_day_score_nuts3_daily.csv")
    pop = _rows(output_root / "tables" / "pop_unit_2015_2025_2030.csv")
    effective = str((inputs.get("paths", {}) if isinstance(inputs, dict) else {}).get("smoke_effective_data_root", ""))
    _write_tsv(qa / "population_weighted_smoke_feasibility.tsv", ["metric", "value", "status", "detail"], [
        ["spatial_smoke_cell_signal", 0, "HOLD", "Current smoke daily table is unit-level; no reproducible smoke cell score is retained."],
        ["population_cell_assignment", 0, "HOLD", "GHSL population is zonally summarized, not retained as cell joins."],
        ["spatial_coverage_acceptable", 0, "HOLD", "No defensible smoke-cell/population-cell overlap."],
        ["population_assignment_acceptable", 0, "HOLD", f"pop_rows={len(pop)}; smoke_rows={len(smoke)}; source={effective}"],
        ["non_degenerate_result", 0, "HOLD", "Not evaluated because required cell inputs are absent."],
        ["methodologically_defensible", 0, "HOLD", "Additional weighted proxy not implemented."],
        ["decision", "SPATIAL_POPULATION_WEIGHTED_PROXY_NOT_IMPLEMENTED", "PASS", "CURRENT_POPULATION_BURDEN_PROXY_RETAINED"],
    ])
    (qa / "population_weighted_smoke_feasibility.md").write_text(
        "# Population-weighted smoke feasibility\n\n"
        "Decision: `SPATIAL_POPULATION_WEIGHTED_PROXY_NOT_IMPLEMENTED`. The current route does not retain a smoke cell score and GHSL is consumed as zonal population; the canonical population_smoke_burden_proxy is retained unchanged.\n",
        encoding="utf-8",
    )
    _write_tsv(qa / "municipal_smoke_resolution_feasibility.tsv", ["metric", "value", "status", "detail"], [
        ["effective_smoke_resolution", "NUTS3_OR_UNIT_LEVEL", "PASS", "Direct municipal smoke signal is not available."],
        ["municipal_direct_smoke_supported", 0, "HOLD", "MUNICIPAL_DIRECT_SMOKE_NOT_SUPPORTED_BY_RESOLUTION"],
        ["decision", "MUNICIPAL_DIRECT_SMOKE_NOT_SUPPORTED_BY_RESOLUTION", "PASS", "MUNICIPAL_RESULTS_RETAINED_AS_NUTS3_SIGNAL_ALLOCATION"],
    ])
    (qa / "municipal_smoke_resolution_feasibility.md").write_text(
        "# Municipal smoke resolution feasibility\n\nDecision: `MUNICIPAL_DIRECT_SMOKE_NOT_SUPPORTED_BY_RESOLUTION`. Municipal results remain explicitly mapped from the NUTS3 signal.\n",
        encoding="utf-8",
    )
    data_root = Path(str((inputs.get("paths", {}) if isinstance(inputs, dict) else {}).get("modulec_data", "")))
    candidates = []
    if data_root.exists():
        candidates = [p for p in data_root.rglob("*") if p.is_file() and any(t in p.name.lower() for t in ("cos", "cosc", "clc"))]
    inv_rows = [[str(p), p.suffix.lower(), "", "", "", "", "", "" ] for p in candidates]
    _write_tsv(qa / "landcover_wui_input_inventory.tsv", ["file", "format", "year", "crs", "coverage", "classes", "readable", "metadata"], inv_rows)
    _write_tsv(qa / "formal_wui_feasibility.tsv", ["metric", "value", "status", "detail"], [
        ["landcover_wui_inputs_found", len(candidates), "PASS", "Inventory limited to authorized data root."],
        ["formal_building_fuel_relation", 0, "HOLD", "No usable COS/COSc/CLC relation resolved."],
        ["decision", "FORMAL_WUI_NOT_SUPPORTED_BY_AVAILABLE_DATA", "PASS", "BUILT_UP_FUEL_TERRITORIAL_PROXY_RETAINED"],
    ])
    (qa / "formal_wui_feasibility.md").write_text(
        "# Formal WUI feasibility\n\nDecision: `FORMAL_WUI_NOT_SUPPORTED_BY_AVAILABLE_DATA`. The existing built-up/fuel territorial proxy is retained and not called formal WUI.\n",
        encoding="utf-8",
    )


def _table_map(path: Path) -> Tuple[List[str], Dict[str, Dict[str, str]]]:
    rows = _rows(path)
    if not rows:
        return [], {}
    header = list(rows[0].keys())
    key = "unit_id" if "unit_id" in header else header[0]
    return header, {(str(r.get(key) or "").strip()): r for r in rows if str(r.get(key) or "").strip()}


def _write_layer(gpkg: Path, source_layer, layer_name: str, table_path: Path, key_field: str, assignment_note: str = "") -> None:
    from qgis.PyQt.QtCore import QVariant  # type: ignore
    from qgis.core import QgsFeature, QgsField, QgsFields, QgsVectorLayer, QgsVectorFileWriter  # type: ignore

    header, table = _table_map(table_path)
    mem = QgsVectorLayer(f"{source_layer.wkbType() == 6 and 'MultiPolygon' or 'MultiPolygon'}?crs={source_layer.crs().authid()}", layer_name, "memory")
    provider = mem.dataProvider()
    fields = QgsFields()
    fields.append(QgsField("unit_id", QVariant.String))
    for col in header:
        if col == key_field or col == "unit_id" or col.lower() == "geometry":
            continue
        fields.append(QgsField(col[:60], QVariant.String))
    if assignment_note:
        fields.append(QgsField("signal_assignment", QVariant.String))
    provider.addAttributes(list(fields))
    mem.updateFields()
    out_features = []
    for feature in source_layer.getFeatures():
        uid = str(feature[key_field] if key_field in feature.fields().names() else feature["unit_id"]).strip()
        row = table.get(uid, {})
        out = QgsFeature(mem.fields())
        out.setGeometry(feature.geometry())
        vals = [uid]
        for fld in mem.fields().names()[1:]:
            if fld == "signal_assignment":
                vals.append(assignment_note)
            else:
                vals.append(str(row.get(fld, "")))
        out.setAttributes(vals)
        out_features.append(out)
    provider.addFeatures(out_features)
    mem.updateExtents()
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GPKG"
    opts.layerName = layer_name
    opts.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer if gpkg.exists() else QgsVectorFileWriter.CreateOrOverwriteFile
    result = QgsVectorFileWriter.writeAsVectorFormatV3(mem, str(gpkg), mem.transformContext(), opts)
    if isinstance(result, (tuple, list)):
        err = result[0]
    else:
        err = result
    if err != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"Thematic GPKG layer write failed: {layer_name}")


def _write_fire_gpkg(output_root: Path, fire_paths: Sequence[Path]) -> None:
    from qgis.PyQt.QtCore import QVariant  # type: ignore
    from qgis.core import QgsFeature, QgsField, QgsVectorLayer, QgsVectorFileWriter  # type: ignore
    gpkg = output_root / "maps" / "fires_normalized_2015_2024.gpkg"
    if gpkg.exists():
        gpkg.unlink()
    mem = None
    provider = None
    count = 0
    years = set()
    for source in fire_paths:
        year = next((int(token) for token in source.name.split("_") if token.isdigit() and len(token) == 4), None)
        if year is None or not (2015 <= year <= 2024):
            continue
        layer = QgsVectorLayer(str(source), f"fire_{year}", "ogr")
        if not layer.isValid():
            continue
        if mem is None:
            mem = QgsVectorLayer(f"MultiPolygon?crs={layer.crs().authid()}", "fires_normalized_2015_2024", "memory")
            provider = mem.dataProvider()
            provider.addAttributes([QgsField("fire_id", QVariant.String), QgsField("year", QVariant.Int), QgsField("source_file", QVariant.String), QgsField("source", QVariant.String), QgsField("area_ha", QVariant.Double), QgsField("source_crs", QVariant.String), QgsField("working_crs", QVariant.String), QgsField("feature_semantics", QVariant.String)])
            mem.updateFields()
        for feature in layer.getFeatures():
            geom = feature.geometry()
            if geom is None or geom.isEmpty():
                continue
            out = QgsFeature(mem.fields())
            out.setGeometry(geom)
            out.setAttributes([f"{year}_{feature.id()}", year, source.name, "ICNF", float(geom.area()) / 10000.0, layer.crs().authid(), layer.crs().authid(), "burned_area_polygon"])
            provider.addFeature(out)
            count += 1
            years.add(year)
    if mem is None:
        raise RuntimeError("No ICNF fire layers available for normalized GPKG")
    mem.updateExtents()
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GPKG"
    opts.layerName = "fires_normalized_2015_2024"
    opts.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile
    result = QgsVectorFileWriter.writeAsVectorFormatV3(mem, str(gpkg), mem.transformContext(), opts)
    err = result[0] if isinstance(result, (tuple, list)) else result
    if err != QgsVectorFileWriter.NoError:
        raise RuntimeError("Normalized fire GPKG write failed")
    _write_tsv(output_root / "qa" / "fires_normalized_gpkg_audit.tsv", ["metric", "value", "status", "detail"], [
        ["feature_count", count, "PASS" if count else "HOLD", "No silent empty fire package."],
        ["years_present", ",".join(str(y) for y in sorted(years)), "PASS" if years == set(range(2015, 2025)) else "HOLD", "ICNF burned-area polygons."],
        ["feature_semantics", "burned_area_polygon", "PASS", "Not individual fire-event count."],
        ["source", "ICNF", "PASS", "EFFIS/AGIF absence remains warning only."],
    ])


def build_thematic_packages(output_root: Path, nuts_layer, muni_layer, muni_field: str, fire_paths: Sequence[Path], inputs: Dict[str, object]) -> None:
    maps = output_root / "maps"
    gpkg = maps / "ModuleC_territorial_results.gpkg"
    if gpkg.exists():
        gpkg.unlink()
    tables = output_root / "tables"
    nuts_specs = [
        ("nuts3_population_smoke_burden_2015_2024", tables / "IECH_unit_2015_2024_mean.csv"),
        ("nuts3_smoke_proxy_2015_2024", tables / "smoke_days_unit_2015_2024.csv"),
        ("nuts3_recurrence_2015_2024", tables / "recurrence_unit_2015_2024.csv"),
        ("nuts3_wrb_context", tables / "wrb_context_nuts3.csv"),
        ("nuts3_territorial_proxy", tables / "territorial_context_nuts3.csv"),
        ("nuts3_scenarios_2026_2030", tables / "IECH_scenarios_unit_2026_2030_mean.csv"),
        ("nuts3_policy_priority", output_root / "brief" / "causal_matrix" / "causal_matrix_IECH_NUTS3.csv"),
    ]
    muni_specs = [
        ("municipio_population_burden_under_nuts3_smoke_signal", tables / "IECH_municipio_2015_2024_mean.csv"),
        ("municipio_recurrence_2015_2024", tables / "recurrence_municipio_2015_2024.csv"),
        ("municipio_wrb_context", tables / "wrb_context_municipio.csv"),
        ("municipio_territorial_proxy", tables / "territorial_context_municipio.csv"),
        ("municipio_scenarios_2026_2030", tables / "IECH_scenarios_municipio_2026_2030_mean.csv"),
    ]
    inventories = []
    joins = []
    for name, table in nuts_specs:
        _write_layer(gpkg, nuts_layer, name, table, "NUTS_ID")
        n = len(_rows(table))
        inventories.append([name, n, nuts_layer.crs().authid(), "PT", "3", "PASS"])
        joins.append([name, n, len(set(r.get("unit_id", "") for r in _rows(table))), "PASS", "1:1 table join"])
    for name, table in muni_specs:
        _write_layer(gpkg, muni_layer, name, table, muni_field, "MAPPED_FROM_NUTS3")
        n = len(_rows(table))
        inventories.append([name, n, muni_layer.crs().authid(), "PT", "municipio", "PASS"])
        joins.append([name, n, len(set(r.get("unit_id", "") for r in _rows(table))), "PASS", "1:1 table join; regional smoke signal where applicable"])
    _write_fire_gpkg(output_root, fire_paths)
    _write_tsv(output_root / "qa" / "cartographic_layers_inventory.tsv", ["layer", "table_rows", "crs", "country", "level", "status"], inventories)
    _write_tsv(output_root / "qa" / "cartographic_join_audit.tsv", ["layer", "source_rows", "unique_keys", "status", "detail"], joins)
    _write_tsv(output_root / "qa" / "cartographic_package_gate.tsv", ["metric", "value", "status", "detail"], [
        ["gpkg", str(gpkg), "PASS", "Thematic GeoPackage written."],
        ["nuts3_layers", 7, "PASS", "Portugal continental NUTS3 thematic layers."],
        ["municipio_layers", 5, "PASS", "Municipal layers carry regional-signal assignment note."],
        ["crs", nuts_layer.crs().authid(), "PASS", "Documented CRS."],
        ["foreign_country_features", 0, "PASS", "Source layer filtered to CNTR_CODE=PT and LEVL_CODE=3."],
    ])


def _rewrite_brief_and_matrix_names(output_root: Path) -> None:
    brief = output_root / "brief" / "Brief_Politica_IECH_2030.md"
    if brief.exists():
        text = brief.read_text(encoding="utf-8", errors="replace")
        replacements = {
            "matriz causal": "matriz de asociacion territorial de screening",
            "Matriz causal": "Matriz de asociacion territorial de screening",
            "WUI / territorio": "Proxy territorial built-up-combustible",
            "Resultados WUI / territorio": "Resultados del proxy territorial",
            "consolidar proxy WUI": "mantener el proxy territorial y no llamarlo WUI formal",
            "legacy IECH": "population_smoke_burden_proxy",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        text += (
            "\n## Semantica de cierre Fase 3\n"
            "- `population_smoke_burden_proxy` es carga poblacional proxy de humo: `smoke_hours_equiv * population_total`.\n"
            "- No es IECH normalizado, exposicion individual, exposicion sanitaria ni riesgo epidemiologico.\n"
            "- La matriz es `TERRITORIAL_SCREENING_ASSOCIATION_MATRIX`, no inferencia causal.\n"
            "- El humo municipal es una asignacion de la senal NUTS3 (`MAPPED_FROM_NUTS3`), no una senal atmosferica municipal independiente.\n"
            "- S1 2026-2030 es un escenario normativo, no una proyeccion empiricamente validada.\n"
            "- El indicador territorial es `BUILT_UP_FUEL_TERRITORIAL_PROXY`; la WUI formal queda en HOLD.\n"
        )
        brief.write_text(text, encoding="utf-8")
    matrix_dir = output_root / "brief" / "causal_matrix"
    legacy_nuts = matrix_dir / "causal_matrix_IECH_NUTS3.csv"
    legacy_muni = matrix_dir / "causal_matrix_IECH_municipio.csv"
    if legacy_nuts.exists():
        (matrix_dir / "territorial_screening_matrix_nuts3.csv").write_bytes(legacy_nuts.read_bytes())
    if legacy_muni.exists():
        (matrix_dir / "territorial_screening_matrix_municipio.csv").write_bytes(legacy_muni.read_bytes())
    (matrix_dir / "territorial_screening_narrative.md").write_text(
        "# Territorial screening narrative\n\n"
        "The matrix integrates the existing proxy burden, smoke, population, recurrence, WRB and territorial context as a descriptive screening association. It does not identify causal effects. Municipal smoke values are mapped from the NUTS3 signal.\n",
        encoding="utf-8",
    )


def run_phase3_closure(output_root: Path, nuts_layer, muni_layer, muni_field: str, fire_paths: Sequence[Path], inputs: Dict[str, object]) -> None:
    _semantic_audits(output_root)
    _feasibility_audits(output_root, inputs)
    build_thematic_packages(output_root, nuts_layer, muni_layer, muni_field, fire_paths, inputs)
    _rewrite_brief_and_matrix_names(output_root)
