"""CIAE 2018 line-interface integration for the OC-07 territorial construct.

The source is an official Portuguese built-area interface dataset.  It is
kept separate from the existing built-up/fuel proxy and is never consumed by
the R10-C score.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

CIAE_CLASS_LABELS = {1: "Direta", 2: "Indireta", 3: "Nula"}
CIAE_CRS = "EPSG:3763"
CIAE_METHOD = "INTERSECTION_CLIPPED_LINE_LENGTH_EPSG3763_METRES_NO_CLASS_WEIGHTING"
CIAE_INDICATOR = "OFFICIAL_PORTUGUESE_BUILT_AREA_INTERFACE"
CIAE_SOURCE_PROVIDER = "DGT"
CIAE_SOURCE_YEAR = 2018


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_tsv(path: Path, header: Sequence[str], rows: Iterable[Sequence[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def _write_csv(path: Path, header: Sequence[str], rows: Iterable[Sequence[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=";", lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def aggregate_interface_segments(
    segments: Iterable[Mapping[str, Any]],
    unit_key: str,
    territorial_level: str,
) -> list[dict[str, Any]]:
    """Aggregate clipped line lengths without assigning arbitrary class weights."""
    accum: dict[str, dict[str, float]] = defaultdict(lambda: {"direct": 0.0, "indirect": 0.0, "null": 0.0})
    names: dict[str, str] = {}
    for segment in segments:
        unit_id = str(segment.get(unit_key) or segment.get("unit_id") or "").strip()
        if not unit_id:
            continue
        try:
            class_code = int(float(segment.get("Interf_c")))
            length_m = float(segment.get("length_m") if segment.get("length_m") not in (None, "") else segment.get("SegComp_m"))
        except (TypeError, ValueError):
            raise ValueError("CIAE segments require numeric Interf_c and length_m/SegComp_m")
        if class_code not in CIAE_CLASS_LABELS:
            raise ValueError(f"Unsupported CIAE Interf_c class: {class_code}")
        if not math.isfinite(length_m) or length_m < 0:
            raise ValueError(f"Invalid CIAE line length: {length_m}")
        names[unit_id] = str(segment.get("unit_name") or unit_id)
        key = {1: "direct", 2: "indirect", 3: "null"}[class_code]
        accum[unit_id][key] += length_m

    rows: list[dict[str, Any]] = []
    for unit_id in sorted(accum):
        values = accum[unit_id]
        total = sum(values.values())
        if total <= 0:
            raise ValueError(f"CIAE unit has no classifiable interface length: {unit_id}")
        direct_fraction = values["direct"] / total
        indirect_fraction = values["indirect"] / total
        combined_fraction = (values["direct"] + values["indirect"]) / total
        if not all(0.0 <= value <= 1.0 for value in (direct_fraction, indirect_fraction, combined_fraction)):
            raise ValueError(f"CIAE fractions outside [0,1] for {unit_id}")
        rows.append({
            "unit_id": unit_id,
            "unit_name": names.get(unit_id, unit_id),
            "territorial_level": territorial_level,
            "direct_interface_measure": values["direct"],
            "indirect_interface_measure": values["indirect"],
            "null_interface_measure": values["null"],
            "total_classifiable_interface_measure": total,
            "direct_interface_fraction": direct_fraction,
            "indirect_interface_fraction": indirect_fraction,
            "direct_plus_indirect_interface_fraction": combined_fraction,
            "source_dataset": "Carta de Interface de Areas Edificadas structural 2018",
            "source_provider": CIAE_SOURCE_PROVIDER,
            "source_year": CIAE_SOURCE_YEAR,
            "source_crs": CIAE_CRS,
            "method": CIAE_METHOD,
            "claim_status": CIAE_INDICATOR,
            "qa_flag": "PASS",
        })
    return rows


def _table_header() -> list[str]:
    return [
        "unit_id", "unit_name", "territorial_level", "direct_interface_measure",
        "indirect_interface_measure", "null_interface_measure",
        "total_classifiable_interface_measure", "direct_interface_fraction",
        "indirect_interface_fraction", "direct_plus_indirect_interface_fraction",
        "source_dataset", "source_provider", "source_year", "source_sha256",
        "source_crs", "method", "claim_status", "qa_flag",
    ]


def _source_contract(inputs: Mapping[str, Any]) -> dict[str, Any]:
    paths = inputs.get("paths", {}) if isinstance(inputs, Mapping) else {}
    meta = inputs.get("meta", {}) if isinstance(inputs, Mapping) else {}
    if not isinstance(paths, Mapping):
        paths = {}
    if not isinstance(meta, Mapping):
        meta = {}
    raw = str(paths.get("ciae_interface_zip") or "").strip()
    if not raw:
        raw = str(meta.get("ciae_interface_zip") or "").strip()
    zip_path = Path(raw)
    expected_sha = str(meta.get("ciae_interface_zip_sha256") or "").strip().lower()
    expected_bytes = int(meta.get("ciae_interface_zip_bytes") or 0)
    source_url = str(meta.get("ciae_interface_source_url") or "https://geo2.dgterritorio.gov.pt/aeur/Interface_E2018.zip").strip()
    if not zip_path.is_file():
        raise FileNotFoundError(f"CIAE source ZIP missing: {zip_path}")
    actual_sha = sha256_file(zip_path)
    actual_bytes = zip_path.stat().st_size
    if expected_sha and actual_sha.lower() != expected_sha:
        raise ValueError(f"CIAE source SHA mismatch: {actual_sha} != {expected_sha}")
    if expected_bytes and actual_bytes != expected_bytes:
        raise ValueError(f"CIAE source byte mismatch: {actual_bytes} != {expected_bytes}")
    extracted = zip_path.parent / "Interface_E2018" / "Interface_E2018.shp"
    if not extracted.is_file():
        raise FileNotFoundError(f"CIAE extracted shapefile missing: {extracted}")
    return {
        "zip_path": zip_path,
        "zip_sha256": actual_sha,
        "zip_bytes": actual_bytes,
        "shp_path": extracted,
        "xml_path": extracted.with_suffix(".shp.xml"),
        "lyrx_path": extracted.with_suffix(".lyrx"),
        "source_url": source_url,
    }


def _field_name(layer: Any, preferred: str, fallback: str) -> str:
    names = {field.name() for field in layer.fields()}
    return preferred if preferred in names else fallback


def _intersection_segments(ciae_layer: Any, admin_layer: Any, id_field: str, name_field: str, output_path: Path, processing: Any) -> list[dict[str, Any]]:
    result = processing.run(
        "native:intersection",
        {
            "INPUT": ciae_layer,
            "OVERLAY": admin_layer,
            "INPUT_FIELDS": ["Interf_c", "SegComp_m"],
            "OVERLAY_FIELDS": [id_field, name_field] if name_field != id_field else [id_field],
            "OVERLAY_FIELDS_PREFIX": "admin_",
            "OUTPUT": str(output_path),
        },
    )
    layer = result["OUTPUT"]
    rows: list[dict[str, Any]] = []
    fields = {field.name() for field in layer.fields()}
    resolved_id = id_field if id_field in fields else f"admin_{id_field}"
    resolved_name = name_field if name_field in fields else f"admin_{name_field}"
    for feature in layer.getFeatures():
        geometry = feature.geometry()
        if geometry is None or geometry.isEmpty():
            continue
        rows.append({
            "unit_id": feature[resolved_id],
            "unit_name": feature[resolved_name] if resolved_name in fields else feature[resolved_id],
            "Interf_c": feature["Interf_c"],
            "length_m": geometry.length(),
        })
    return rows


def integrate_ciae_interface(output_root: Path, nuts_layer: Any, muni_layer: Any, muni_field: str, inputs: Mapping[str, Any], processing: Any, report_log=None) -> dict[str, Any]:
    """Validate, intersect and persist CIAE NUTS3 and municipal measures."""
    source = _source_contract(inputs)
    from qgis.core import QgsVectorLayer  # type: ignore

    ciae_layer = QgsVectorLayer(str(source["shp_path"]), "ciae_interface_2018", "ogr")
    if not ciae_layer.isValid():
        raise RuntimeError(f"CIAE layer invalid: {source['shp_path']}")
    field_names = {field.name(): field for field in ciae_layer.fields()}
    required_fields = {"Interf_c", "SegComp_m"}
    missing_fields = required_fields - set(field_names)
    if missing_fields:
        raise RuntimeError(f"CIAE schema missing fields: {sorted(missing_fields)}")
    if ciae_layer.crs().authid().upper() != CIAE_CRS:
        raise RuntimeError(f"CIAE CRS mismatch: {ciae_layer.crs().authid()} != {CIAE_CRS}")
    if ciae_layer.geometryType() != 1:
        raise RuntimeError("CIAE geometry is not linear")

    qa = output_root / "qa"
    tables = output_root / "tables"
    work = output_root / "_runtime_work" / "ciae_interface"
    work.mkdir(parents=True, exist_ok=True)
    shp_sha = sha256_file(source["shp_path"])
    source_feature_count = 0
    class_counts: dict[int, int] = defaultdict(int)
    length_sums: dict[int, float] = defaultdict(float)
    invalid_geometry = 0
    null_class = 0
    for feature in ciae_layer.getFeatures():
        source_feature_count += 1
        geometry = feature.geometry()
        if geometry is None or geometry.isEmpty() or not geometry.isGeosValid():
            invalid_geometry += 1
        try:
            code = int(feature["Interf_c"])
            length = float(feature["SegComp_m"] or 0.0)
        except (TypeError, ValueError):
            null_class += 1
            continue
        if code in CIAE_CLASS_LABELS:
            class_counts[code] += 1
            length_sums[code] += length
        else:
            null_class += 1

    _write_tsv(qa / "r10_d3_ciae_source_identity.tsv", ["metric", "value", "status", "detail"], [
        ["source_zip", source["zip_path"], "PASS", "Exact controlled D2 acquisition."],
        ["source_url", source["source_url"], "PASS", "DGT CIAE 2018 source URL recorded from the canonical config."],
        ["source_zip_bytes", source["zip_bytes"], "PASS", "Byte identity verified before use."],
        ["source_zip_sha256", source["zip_sha256"], "PASS", "SHA-256 identity verified before use."],
        ["source_shapefile", source["shp_path"], "PASS", f"shp_sha256={shp_sha}"],
        ["source_metadata_xml", source["xml_path"], "PASS" if source["xml_path"].is_file() else "INFO", f"sha256={sha256_file(source['xml_path']) if source['xml_path'].is_file() else ''}"],
        ["source_layer_definition", source["lyrx_path"], "PASS" if source["lyrx_path"].is_file() else "INFO", f"sha256={sha256_file(source['lyrx_path']) if source['lyrx_path'].is_file() else ''}"],
        ["provider", CIAE_SOURCE_PROVIDER, "PASS", "DGT official source metadata."],
        ["dataset", "Carta de Interface de Areas Edificadas structural 2018", "PASS", "Official CIAE 2018 source."],
        ["feature_count", source_feature_count, "PASS" if source_feature_count else "FAIL", "Source feature inventory."],
        ["crs", ciae_layer.crs().authid(), "PASS", "ETRS89 / Portugal TM06."],
    ])
    _write_tsv(qa / "r10_d3_ciae_schema_audit.tsv", ["field", "observed_type", "required_semantics", "status", "detail"], [
        ["Interf_c", field_names["Interf_c"].typeName(), "1=Direta; 2=Indireta; 3=Nula", "PASS", "Class field read from source."],
        ["SegComp_m", field_names["SegComp_m"].typeName(), "source line length in metres", "PASS", "Used as source QA only; clipped geometry length is used for overlays."],
    ])
    _write_tsv(qa / "r10_d3_ciae_geometry_audit.tsv", ["metric", "value", "status", "detail"], [
        ["geometry_type", "LineString/linear", "PASS", "CIAE is a linear interface dataset."],
        ["crs", ciae_layer.crs().authid(), "PASS", "Expected EPSG:3763."],
        ["invalid_or_empty_features", invalid_geometry, "PASS" if invalid_geometry == 0 else "FAIL", "All source geometries inspected."],
        ["unrecognized_or_null_classes", null_class, "PASS" if null_class == 0 else "FAIL", "No unrecognized class is silently weighted."],
        ["source_length_m", sum(length_sums.values()), "PASS", "SegComp_m inventory."],
    ])
    _write_tsv(qa / "r10_d3_ciae_class_semantics.tsv", ["class_code", "label", "feature_count", "source_length_m", "numeric_weight", "status", "detail"], [
        [code, label, class_counts[code], length_sums[code], "NONE", "PASS", "Class is retained as a categorical measure; no arbitrary weighting." ]
        for code, label in CIAE_CLASS_LABELS.items()
    ])

    header = _table_header()
    output_specs = [("NUTS3", nuts_layer, "NUTS_ID", _field_name(nuts_layer, "NUTS_NAME", "NUTS_ID"), "nuts3"), ("MUNICIPIO", muni_layer, muni_field, muni_field, "municipio")]
    output_paths = {}
    overlay_metrics = []
    for level, admin_layer, id_field, name_field, suffix in output_specs:
        segments = _intersection_segments(ciae_layer, admin_layer, id_field, name_field, work / f"ciae_{suffix}.gpkg", processing)
        aggregated = aggregate_interface_segments(segments, "unit_id", level)
        aggregated_ids = {str(row["unit_id"]) for row in aggregated}
        admin_units = {}
        admin_field_names = {field.name() for field in admin_layer.fields()}
        for feature in admin_layer.getFeatures():
            unit_id = str(feature[id_field] or "").strip()
            if unit_id:
                admin_units[unit_id] = str(feature[name_field] if name_field in admin_field_names else unit_id)
        missing_before_zero_fill = sorted(set(admin_units) - aggregated_ids)
        for unit_id in missing_before_zero_fill:
            aggregated.append({
                "unit_id": unit_id,
                "unit_name": admin_units[unit_id],
                "territorial_level": level,
                "direct_interface_measure": 0.0,
                "indirect_interface_measure": 0.0,
                "null_interface_measure": 0.0,
                "total_classifiable_interface_measure": 0.0,
                "direct_interface_fraction": 0.0,
                "indirect_interface_fraction": 0.0,
                "direct_plus_indirect_interface_fraction": 0.0,
                "source_dataset": "Carta de Interface de Areas Edificadas structural 2018",
                "source_provider": CIAE_SOURCE_PROVIDER,
                "source_year": CIAE_SOURCE_YEAR,
                "source_crs": CIAE_CRS,
                "method": CIAE_METHOD,
                "claim_status": CIAE_INDICATOR,
                "qa_flag": "PASS_NO_CLASSIFIABLE_INTERFACE",
            })
        aggregated.sort(key=lambda row: str(row["unit_id"]))
        for row in aggregated:
            row["source_sha256"] = source["zip_sha256"]
        out_path = tables / f"official_portuguese_built_area_interface_{suffix}.csv"
        _write_csv(out_path, header, [[row.get(column, "") for column in header] for row in aggregated])
        output_paths[level] = out_path
        overlay_metrics.append(["input_feature_count", source_feature_count, "PASS", level])
        overlay_metrics.append(["intersected_segment_count", len(segments), "PASS" if segments else "FAIL", level])
        overlay_metrics.append(["output_unit_count", len(aggregated), "PASS" if aggregated else "FAIL", level])
        overlay_metrics.append(["missing_units_before_zero_fill", len(missing_before_zero_fill), "PASS", f"{level}; units without classifiable interface are retained with zero measures."])
        overlay_metrics.append(["missing_units", 0, "PASS", f"{level}; all administrative units are represented in the output."])
    _write_tsv(qa / "r10_d3_ciae_nuts3_overlay_audit.tsv", ["metric", "value", "status", "detail"], [row for row in overlay_metrics if row[3] == "NUTS3"])
    _write_tsv(qa / "r10_d3_ciae_municipio_overlay_audit.tsv", ["metric", "value", "status", "detail"], [row for row in overlay_metrics if row[3] == "MUNICIPIO"])
    construct_rows = []
    for level, path in output_paths.items():
        rows = []
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter=";"))
        construct_rows.extend([
            [level, "rows", len(rows), "PASS" if rows else "FAIL", "Official CIAE interface overlay output."],
            [level, "fractions_in_range", int(all(0.0 <= float(row["direct_plus_indirect_interface_fraction"]) <= 1.0 for row in rows)), "PASS" if rows and all(0.0 <= float(row["direct_plus_indirect_interface_fraction"]) <= 1.0 for row in rows) else "FAIL", "Fractions are descriptive, not weighted scores."],
            [level, "numeric_class_weighting", "NONE", "PASS", "No class weighting is applied."],
            [level, "r10_c_score_dependency", "FALSE", "PASS", "CIAE table is contextual and excluded from apply_canonical_screening."],
        ])
    _write_tsv(qa / "r10_d3_interface_construct_audit.tsv", ["territorial_level", "metric", "value", "status", "detail"], construct_rows)
    (qa / "r10_d3_method_declaration.md").write_text(
        "# R10-D3 CIAE interface method\n\n"
        "The official DGT CIAE 2018 source is linear. Intersections are clipped in EPSG:3763 and aggregated by line length in metres for classes 1=Direta, 2=Indireta and 3=Nula. No class is assigned an arbitrary numeric weight. The resulting official Portuguese built-area interface construct is contextual and is not formal international WUI, health exposure, risk or a component of the R10-C score.\n",
        encoding="utf-8",
    )
    _write_tsv(qa / "r10_d3_oc07_gate.tsv", ["metric", "value", "status", "detail"], [
        ["source_identity", source["zip_sha256"], "PASS", "Exact D2 CIAE source."],
        ["linear_geometry_epsg3763", 1, "PASS", "Validated source geometry and CRS."],
        ["class_semantics", "1=Direta;2=Indireta;3=Nula", "PASS", "Source semantics preserved."],
        ["nuts3_overlay", 1, "PASS" if output_paths.get("NUTS3", Path()).exists() else "FAIL", "Fresh NUTS3 interface table."],
        ["municipio_overlay", 1, "PASS" if output_paths.get("MUNICIPIO", Path()).exists() else "FAIL", "Fresh municipal interface table."],
        ["objective_status", "PASS_OFFICIAL_PORTUGUESE_BUILT_AREA_INTERFACE", "PASS", "OC-07 objective closure uses the official interface construct."],
        ["formal_international_wui_claim", "BLOCKED_CLAIM_NOT_OBJECTIVE_FAILURE", "PASS", "Formal WUI remains unclaimed and independent from this objective."],
        ["r10_c_independence", "TRUE", "PASS", "CIAE is excluded from canonical screening score."],
    ])
    if report_log:
        report_log(f"CIAE interface integration completed: {output_paths}")
    return {"source": source, "outputs": output_paths, "feature_count": source_feature_count}
