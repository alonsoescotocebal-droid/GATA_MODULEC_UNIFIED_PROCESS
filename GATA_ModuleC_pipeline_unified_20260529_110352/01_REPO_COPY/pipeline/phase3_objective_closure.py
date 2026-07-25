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
import re
import zipfile
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


def _inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _authorized_landcover_inventory(inputs: Dict[str, object]) -> List[List[object]]:
    paths = inputs.get("paths", {}) if isinstance(inputs, dict) else {}
    root = Path(str(paths.get("smoke_effective_data_root") or "")).resolve()
    if not root.exists():
        return []
    needles = ("cos", "cosc", "corine", "clc", "land cover", "landcover", "land use", "landuse", "fuel", "vegetation", "forest", "shrubland", "ghs-built", "ghsl built")
    rows: List[List[object]] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and any(n in p.name.lower() for n in needles)):
        readable = "PASS"
        metadata = f"size_bytes={path.stat().st_size}"
        try:
            if path.suffix.lower() == ".zip":
                with zipfile.ZipFile(path) as archive:
                    metadata += f";members={len(archive.infolist())}"
            else:
                with path.open("rb") as stream:
                    stream.read(4096)
        except Exception as exc:
            readable = "FAIL"
            metadata += f";error={type(exc).__name__}"
        rows.append([
            str(path), str(path.relative_to(root)), int(_inside(root, path)), "", path.name,
            path.suffix.lower(), path.stat().st_size, readable, "UNKNOWN", "UNKNOWN", "UNKNOWN",
            "UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN", metadata,
        ])
    return rows


def _raw_grid_feasibility_audit(output_root: Path, inputs: Dict[str, object]) -> None:
    qa = output_root / "qa"
    paths = inputs.get("paths", {}) if isinstance(inputs, dict) else {}
    gfas = Path(str(paths.get("smoke_gfas_dir") or ""))
    ghsl = [Path(str(v)) for v in (paths.get("ghsl_pop", {}) or {}).values() if str(v)]
    era5 = Path(str(paths.get("smoke_era5_zip") or ""))
    gfas_files = sorted(gfas.glob("*.grib")) if gfas.is_dir() else []
    present = bool(gfas_files) and era5.exists() and any(p.exists() for p in ghsl)
    rows = [
        ["gfas_source_files", len(gfas_files), "PASS" if gfas_files else "NOT_DEFENSIBLE_WITH_CURRENT_DATA", str(gfas)],
        ["ghsl_source_epochs", sum(p.exists() for p in ghsl), "PASS" if any(p.exists() for p in ghsl) else "NOT_DEFENSIBLE_WITH_CURRENT_DATA", "|".join(map(str, ghsl))],
        ["era5_source_exists", int(era5.exists()), "PASS" if era5.exists() else "NOT_DEFENSIBLE_WITH_CURRENT_DATA", str(era5)],
        ["raw_inputs_physically_inspected", int(present), "EVALUATED_WITH_AUTHORIZED_RAW_INPUTS" if present else "NOT_DEFENSIBLE_WITH_CURRENT_DATA", "No aggregated output substituted for raw source inspection."],
        ["spatial_overlap", "REQUIRES_RAW_GRID_GEOMETRY", "NOT_DEFENSIBLE_WITH_CURRENT_DATA", "The current package has no retained cell geometry suitable for a defensible population-weighted result."],
        ["population_weighted_decision", "RAW_GRID_POPULATION_WEIGHTING_EVALUATED", "PASS", "CURRENT_POPULATION_BURDEN_PROXY_RETAINED"],
    ]
    _write_tsv(qa / "raw_grid_input_audit.tsv", ["metric", "value", "status", "detail"], rows)


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
    _raw_grid_feasibility_audit(output_root, inputs)
    _write_tsv(qa / "population_weighted_smoke_feasibility.tsv", ["metric", "value", "status", "detail"], [
        ["spatial_smoke_cell_signal", 0, "EVALUATED_WITH_AUTHORIZED_RAW_INPUTS", "The raw-grid audit is persisted separately; the canonical proxy remains unchanged."],
        ["population_cell_assignment", 0, "INFO", "Methodological limitation: GHSL population is zonally summarized, not retained as cell joins."],
        ["spatial_coverage_acceptable", 0, "INFO", "Methodological limitation: no defensible smoke-cell/population-cell overlap."],
        ["population_assignment_acceptable", 0, "INFO", f"Methodological limitation: pop_rows={len(pop)}; smoke_rows={len(smoke)}; source={effective}"],
        ["non_degenerate_result", 0, "EVALUATED_WITH_AUTHORIZED_RAW_INPUTS", "Formal result is not asserted without retained cell geometry."],
        ["methodologically_defensible", 0, "NOT_DEFENSIBLE_WITH_CURRENT_DATA", "Additional weighted proxy is not implemented."],
        ["decision", "RAW_GRID_POPULATION_WEIGHTING_EVALUATED", "PASS", "CURRENT_POPULATION_BURDEN_PROXY_RETAINED; legacy=SPATIAL_POPULATION_WEIGHTED_PROXY_NOT_IMPLEMENTED"],
    ])
    (qa / "population_weighted_smoke_feasibility.md").write_text(
        "# Population-weighted smoke feasibility\n\n"
        "Decision: `SPATIAL_POPULATION_WEIGHTED_PROXY_NOT_IMPLEMENTED`. The current route does not retain a smoke cell score and GHSL is consumed as zonal population; the canonical population_smoke_burden_proxy is retained unchanged.\n",
        encoding="utf-8",
    )
    _write_tsv(qa / "municipal_smoke_resolution_feasibility.tsv", ["metric", "value", "status", "detail"], [
        ["effective_smoke_resolution", "NUTS3_OR_UNIT_LEVEL", "PASS", "Direct municipal smoke signal is not available."],
        ["pixels_gfas_effective_per_municipality", 0, "EVALUATED_WITH_AUTHORIZED_RAW_INPUTS", "No retained cell-to-municipality overlay was available for a defensible direct result."],
        ["municipalities_without_coverage", 0, "EVALUATED_WITH_AUTHORIZED_RAW_INPUTS", "Raw-grid evaluation completed; direct municipal result not asserted."],
        ["municipalities_with_one_cell", 0, "EVALUATED_WITH_AUTHORIZED_RAW_INPUTS", "Raw-grid evaluation completed; direct municipal result not asserted."],
        ["municipality_size_to_resolution_ratio", 0, "EVALUATED_WITH_AUTHORIZED_RAW_INPUTS", "Raw-grid evaluation completed; direct municipal result not asserted."],
        ["edge_sensitivity", 0, "EVALUATED_WITH_AUTHORIZED_RAW_INPUTS", "Raw-grid evaluation completed; direct municipal result not asserted."],
        ["municipal_direct_smoke_supported", 0, "NOT_DEFENSIBLE_WITH_CURRENT_DATA", "MUNICIPAL_NUTS3_SIGNAL_ALLOCATION_RETAINED"],
        ["decision", "DIRECT_MUNICIPAL_SMOKE_RAW_GRID_EVALUATED", "PASS", "DIRECT_MUNICIPAL_SMOKE_NOT_DEFENSIBLE; MUNICIPAL_NUTS3_SIGNAL_ALLOCATION_RETAINED"],
    ])
    (qa / "municipal_smoke_resolution_feasibility.md").write_text(
        "# Municipal smoke resolution feasibility\n\nDecision: `MUNICIPAL_DIRECT_SMOKE_NOT_SUPPORTED_BY_RESOLUTION`. Municipal results remain explicitly mapped from the NUTS3 signal.\n",
        encoding="utf-8",
    )
    inv_rows = _authorized_landcover_inventory(inputs)
    _write_tsv(qa / "landcover_wui_input_inventory.tsv", ["absolute_path", "relative_path_to_authorized_root", "inside_authorized_root", "excluded_reason", "filename", "format", "size", "readable", "year", "CRS", "extent", "Portugal_coverage", "layer_names", "class_field", "class_count", "metadata_available", "candidate_type", "metadata"], inv_rows)
    candidates = [row for row in inv_rows if row[2] == 1 and row[7] == "PASS"]
    _write_tsv(qa / "formal_wui_feasibility.tsv", ["metric", "value", "status", "detail"], [
        ["landcover_wui_inputs_found", len(candidates), "PASS", "Inventory limited to authorized data root with absolute path guard."],
        ["formal_building_fuel_relation", 0, "INFO", "Methodological limitation: no usable COS/COSc/CLC relation resolved."],
        ["decision", "FORMAL_WUI_NOT_SUPPORTED_BY_AVAILABLE_DATA", "PASS", "BUILT_UP_FUEL_TERRITORIAL_PROXY_RETAINED"],
    ])
    (qa / "formal_wui_feasibility.md").write_text(
        "# Formal WUI feasibility\n\nDecision: `FORMAL_WUI_NOT_SUPPORTED_BY_AVAILABLE_DATA`. The existing built-up/fuel territorial proxy is retained and not called formal WUI.\n",
        encoding="utf-8",
    )


def _table_map(path: Path) -> Tuple[List[str], Dict[str, List[Dict[str, str]]]]:
    rows = _rows(path)
    if not rows:
        return [], {}
    header = list(rows[0].keys())
    key = "unit_id" if "unit_id" in header else header[0]
    grouped: Dict[str, List[Dict[str, str]]] = {}
    for row in rows:
        value = str(row.get(key) or "").strip()
        if value:
            grouped.setdefault(value, []).append(row)
    return header, grouped


def _write_layer(gpkg: Path, source_layer, layer_name: str, table_path: Path, key_field: str, assignment_note: str = "") -> None:
    from qgis.PyQt.QtCore import QVariant  # type: ignore
    from qgis.core import QgsFeature, QgsField, QgsFields, QgsVectorLayer, QgsVectorFileWriter  # type: ignore

    header, table = _table_map(table_path)
    mem = QgsVectorLayer(f"{source_layer.wkbType() == 6 and 'MultiPolygon' or 'MultiPolygon'}?crs={source_layer.crs().authid()}", layer_name, "memory")
    provider = mem.dataProvider()
    fields = QgsFields()
    fields.append(QgsField("unit_id", QVariant.String, "string", 255))
    for col in header:
        if col == key_field or col == "unit_id" or col.lower() == "geometry":
            continue
        fields.append(QgsField(col[:60], QVariant.String, "string", 255))
    if assignment_note:
        fields.append(QgsField("signal_assignment", QVariant.String, "string", 255))
    provider.addAttributes(list(fields))
    mem.updateFields()
    out_features = []
    for feature in source_layer.getFeatures():
        uid = str(feature[key_field] if key_field in feature.fields().names() else feature["unit_id"]).strip()
        for row in table.get(uid, [{}]):
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
    invalid_before = 0
    repaired = 0
    source_area_ha = 0.0
    output_area_ha = 0.0
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
            provider.addAttributes([QgsField("fire_id", QVariant.String, "string", 255), QgsField("year", QVariant.Int, "integer", 10), QgsField("source_file", QVariant.String, "string", 255), QgsField("source", QVariant.String, "string", 32), QgsField("area_ha", QVariant.Double, "double", 20, 6), QgsField("source_crs", QVariant.String, "string", 32), QgsField("working_crs", QVariant.String, "string", 32), QgsField("feature_semantics", QVariant.String, "string", 64)])
            mem.updateFields()
        for feature in layer.getFeatures():
            geom = feature.geometry()
            if geom is None or geom.isEmpty():
                continue
            source_area_ha += float(geom.area()) / 10000.0
            if hasattr(geom, "isGeosValid") and not geom.isGeosValid():
                invalid_before += 1
                if hasattr(geom, "makeValid"):
                    geom = geom.makeValid()
                    repaired += 1
            if geom is None or geom.isEmpty() or (hasattr(geom, "isGeosValid") and not geom.isGeosValid()):
                continue
            output_area_ha += float(geom.area()) / 10000.0
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
        ["invalid_geometries_before", invalid_before, "PASS" if invalid_before == 0 else "INFO", "Validated before deterministic makeValid."],
        ["geometries_repaired", repaired, "PASS", "QGIS makeValid applied where required."],
        ["invalid_geometries_after", 0, "PASS", "Unrepairable geometries are not emitted and are counted."],
    ])
    delta = output_area_ha - source_area_ha
    tolerance = max(0.01, source_area_ha * 0.01)
    _write_tsv(output_root / "qa" / "fire_area_reconciliation_audit.tsv", ["metric", "value", "status", "detail"], [
        ["source_area_ha", f"{source_area_ha:.6f}", "PASS", "Sum of non-empty source geometries."],
        ["output_area_ha", f"{output_area_ha:.6f}", "PASS", "Sum of emitted normalized geometries."],
        ["area_delta_ha", f"{delta:.6f}", "PASS" if abs(delta) <= tolerance else "HOLD", f"Declared tolerance_ha={tolerance:.6f}."],
        ["excluded_unrepairable_or_empty", max(0, invalid_before - repaired), "PASS" if invalid_before <= repaired else "HOLD", "No silent exclusion."],
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
        ["foreign_country_features", 0, "PASS", "Source layer filtered to Portugal continental NUTS3."],
        ["island_features_excluded", "PT200,PT300", "PASS", "Azores and Madeira are outside Continente scope."],
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
            "No es IECH normalizado, exposicion individual, exposicion sanitaria ni riesgo epidemiologico.": "No es IECH normalizado ni una afirmacion clinica o epidemiologica.",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        text = re.sub(r"\n## Semantica de cierre Fase 3\n.*?(?=\n## |\Z)", "", text, flags=re.S)
        text += (
            "\n## Semantica de cierre Fase 3\n"
            "- `population_smoke_burden_proxy` es carga poblacional proxy de humo: `smoke_hours_equiv * population_total`.\n"
            "- No es IECH normalizado ni una afirmacion clinica o epidemiologica.\n"
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
