from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from pipeline.ciae_interface import (
    CIAE_METHOD,
    _source_contract,
    aggregate_interface_segments,
)
from pipeline.moduleC_pipeline_v2 import Report, create_r10_final_audit_capsule
from pipeline.screening_r10c import apply_canonical_screening
from pipeline.validate_modulec_objectives_canon import _check_official_interface_quality


def test_ciae_source_identity_requires_exact_bytes_and_sha(tmp_path: Path) -> None:
    source_dir = tmp_path / "Interface_E2018"
    source_dir.mkdir()
    (source_dir / "Interface_E2018.shp").write_bytes(b"shape placeholder")
    archive = tmp_path / "Interface_E2018.zip"
    archive.write_bytes(b"controlled source")
    import hashlib

    contract = {
        "paths": {"ciae_interface_zip": str(archive)},
        "meta": {
            "ciae_interface_zip_bytes": archive.stat().st_size,
            "ciae_interface_zip_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        },
    }
    resolved = _source_contract(contract)
    assert resolved["zip_bytes"] == archive.stat().st_size
    assert resolved["shp_path"].is_file()

    contract["meta"]["ciae_interface_zip_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="SHA mismatch"):
        _source_contract(contract)


def test_ciae_classes_and_line_measures_are_reproducible_and_unweighted() -> None:
    segments = [
        {"unit_id": "N1", "unit_name": "North", "Interf_c": 1, "length_m": 30.0},
        {"unit_id": "N1", "unit_name": "North", "Interf_c": 2, "length_m": 20.0},
        {"unit_id": "N1", "unit_name": "North", "Interf_c": 3, "length_m": 10.0},
    ]
    first = aggregate_interface_segments(segments, "unit_id", "NUTS3")
    second = aggregate_interface_segments(list(reversed(segments)), "unit_id", "NUTS3")
    assert first == second
    row = first[0]
    assert row["direct_interface_measure"] == 30.0
    assert row["indirect_interface_measure"] == 20.0
    assert row["null_interface_measure"] == 10.0
    assert row["direct_plus_indirect_interface_fraction"] == pytest.approx(5.0 / 6.0)
    assert row["method"] == CIAE_METHOD
    assert "weight" in CIAE_METHOD.lower()
    with pytest.raises(ValueError, match="Unsupported CIAE"):
        aggregate_interface_segments([{"unit_id": "N1", "Interf_c": 9, "length_m": 1}], "unit_id", "NUTS3")


def test_ciae_construct_is_independent_of_r10c_score() -> None:
    base = [
        {"unit_id": "A", "population_smoke_day_burden_proxy_mean_2015_2024": 10, "recurrence_score": 0.1},
        {"unit_id": "B", "population_smoke_day_burden_proxy_mean_2015_2024": 20, "recurrence_score": 0.9},
    ]
    changed = [dict(row, direct_plus_indirect_interface_fraction=0.99, wui_proxy=999999) for row in base]
    first = apply_canonical_screening(base, "NUTS3")
    second = apply_canonical_screening(changed, "NUTS3")
    for left, right in zip(first, second):
        assert left["screening_priority_score"] == right["screening_priority_score"]
        assert left["policy_priority"] == right["policy_priority"]
        assert left["burden_priority_rank"] == right["burden_priority_rank"]
        assert left["recurrence_priority_rank"] == right["recurrence_priority_rank"]


def test_oc07_requires_fresh_official_interface_outputs(tmp_path: Path) -> None:
    root = tmp_path / "out"
    assert not _check_official_interface_quality(root)[0]
    (root / "qa").mkdir(parents=True)
    (root / "tables").mkdir(parents=True)
    (root / "qa" / "r10_d3_oc07_gate.tsv").write_text(
        "metric\tvalue\tstatus\tdetail\n"
        "objective_status\tPASS_OFFICIAL_PORTUGUESE_BUILT_AREA_INTERFACE\tPASS\tok\n"
        "formal_international_wui_claim\tBLOCKED_CLAIM_NOT_OBJECTIVE_FAILURE\tPASS\tok\n",
        encoding="utf-8",
    )
    header = "unit_id;unit_name;territorial_level;direct_interface_measure;indirect_interface_measure;null_interface_measure;total_classifiable_interface_measure;direct_interface_fraction;indirect_interface_fraction;direct_plus_indirect_interface_fraction;source_sha256;source_crs;method;qa_flag\n"
    row = "N1;North;NUTS3;1;1;1;3;0.33;0.33;0.66;abc;EPSG:3763;INTERSECTION_CLIPPED_LINE_LENGTH_EPSG3763_METRES_NO_CLASS_WEIGHTING;PASS\n"
    (root / "tables" / "official_portuguese_built_area_interface_nuts3.csv").write_text(header + row, encoding="utf-8")
    (root / "tables" / "official_portuguese_built_area_interface_municipio.csv").write_text(header + row.replace("N1;North;NUTS3", "M1;Municipality;MUNICIPIO"), encoding="utf-8")
    assert _check_official_interface_quality(root)[0]


def test_final_audit_capsule_is_compact_and_self_manifested(tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    (root / "qa").mkdir(parents=True)
    (root / "qa" / "path_scope_guard_report.tsv").write_text("metric\tstatus\npath\tPASS\n", encoding="utf-8")
    deliver = root / "deliverables_step9"
    deliver.mkdir(parents=True)
    (deliver / "final_manifest.json").write_text("[]", encoding="utf-8")
    (deliver / "final_manifest_recursive_audit.tsv").write_text("relative_path\tbytes\tsha256\n", encoding="utf-8")
    (deliver / "final_sha256_checkpoints.txt").write_text("STEP9_FINAL_MASTER_PACK checkpoint\n", encoding="utf-8")
    capsule = create_r10_final_audit_capsule(root, Report(root / "qa" / "report.txt"))
    assert capsule.name.startswith("R10_FINAL_AUDIT_CAPSULE_")
    assert capsule.suffix == ".zip"
    assert capsule.with_suffix(".sha256").is_file()
    gate = (root / "qa" / "audit_capsule_gate.tsv").read_text(encoding="utf-8")
    assert "AUDIT_CAPSULE_GATE\tPASS" in gate
    import zipfile

    with zipfile.ZipFile(capsule) as archive:
        names = archive.namelist()
        assert "audit_capsule_manifest.tsv" in names
        assert not any(name.lower().endswith((".grib", ".gpkg", ".shp", ".zip")) for name in names)
