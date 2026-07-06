import sys
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import validate_modulec_objectives_canon as mod  # type: ignore

    return mod


def _write_wrb_tables(output_root: Path, note: str) -> None:
    tables = output_root / "tables"
    qa = output_root / "qa"
    tables.mkdir(parents=True, exist_ok=True)
    qa.mkdir(parents=True, exist_ok=True)
    (tables / "wrb_context_nuts3.csv").write_text(
        "unit_id;dominant_wrb_class;dominant_wrb_share;top_wrb_classes;wrb_context_note;wrb_source;wrb_missing_flag\n"
        f"PT11;Cambisols;0.70;Cambisols|Luvisols;{note};WRB_working_TM06_from_tiles.vrt;0\n",
        encoding="utf-8",
    )
    (tables / "wrb_context_municipio.csv").write_text(
        "unit_id;dominant_wrb_class;dominant_wrb_share;top_wrb_classes;wrb_context_note;wrb_source;wrb_missing_flag\n"
        f"0101;Cambisols;0.70;Cambisols|Luvisols;{note};WRB_working_TM06_from_tiles.vrt;0\n",
        encoding="utf-8",
    )
    (qa / "wrb_2022_prevalidation.tsv").write_text(
        "metric\tvalue\tstatus\tnote\n"
        "computed_multiclass\t2\tPASS\tok\n"
        "computed_has_cambisols\t1\tPASS\tok\n"
        "computed_has_luvisols\t1\tPASS\tok\n"
        "class_set_match_reference\t1\tPASS\tok\n",
        encoding="utf-8",
    )


def test_check_wrb_quality_passes_with_prevalidated_multiclass_route(tmp_path):
    mod = _load_module()
    _write_wrb_tables(tmp_path, "Contexto edafico territorial (WRB) sobre admin_unit intersect annual_burned_area intersect WRB_working_TM06_from_tiles.")

    ok, reason = mod._check_wrb_quality(tmp_path)

    assert ok is True
    assert "prevalidation=PASS" in reason


def test_check_wrb_quality_blocks_fallback_notes(tmp_path):
    mod = _load_module()
    _write_wrb_tables(tmp_path, "Fallback WRB global class from raster metadata after centroid extraction.")

    ok, reason = mod._check_wrb_quality(tmp_path)

    assert ok is False
    assert "fallback" in reason.lower()
