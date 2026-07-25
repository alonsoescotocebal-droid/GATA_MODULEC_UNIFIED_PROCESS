import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from pipeline.phase3_objective_closure import _feasibility_audits
import moduleC_pipeline_v2 as pipeline


def test_phase3c_wui_inventory_is_authorized_and_metadata_complete(tmp_path):
    data = tmp_path / "data"
    output = tmp_path / "output"
    data.mkdir()
    (data / "COS_valid.tif").write_bytes(b"source")
    (tmp_path / "COS_outside.tif").write_bytes(b"outside")
    _feasibility_audits(output, {"paths": {"smoke_effective_data_root": str(data), "ghsl_pop": {}}})
    rows = list(csv.DictReader((output / "qa" / "landcover_wui_input_inventory.tsv").open(encoding="utf-8"), delimiter="\t"))
    assert len(rows) == 1
    assert rows[0]["inside_authorized_root"] == "1"
    assert "absolute_path" in rows[0]


def test_phase3c_raw_grid_audit_does_not_use_aggregates_as_input(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    gfas = data / "gfas"
    gfas.mkdir()
    (gfas / "GFAS_2015.grib").write_bytes(b"raw")
    era5 = data / "era5.zip"
    era5.write_bytes(b"raw")
    _feasibility_audits(tmp_path / "output", {"paths": {"smoke_effective_data_root": str(data), "smoke_gfas_dir": str(gfas), "smoke_era5_zip": str(era5), "ghsl_pop": {"2020": str(data / "ghsl.zip")}}})
    text = (tmp_path / "output" / "qa" / "raw_grid_input_audit.tsv").read_text(encoding="utf-8")
    assert "RAW_GRID_POPULATION_WEIGHTING_EVALUATED" in text
    assert "CURRENT_POPULATION_BURDEN_PROXY_RETAINED" in text


def test_phase3c_warning_inventory_includes_external_logs(tmp_path):
    (tmp_path / "qa").mkdir()
    (tmp_path / "launcher_stdout.txt").write_text("SyntaxWarning: external\n", encoding="utf-8")
    pipeline.refresh_warning_inventory_from_runtime_logs(tmp_path / "03_outputs")
    text = (tmp_path / "03_outputs" / "qa" / "warning_inventory.tsv").read_text(encoding="utf-8-sig")
    assert "LAUNCHER_STDOUT" in text
    assert "warning_id" in text


def test_phase3c_brief_encoding_audit(tmp_path):
    brief = tmp_path / "brief" / "Brief_Politica_IECH_2030.md"
    brief.parent.mkdir(parents=True)
    brief.write_text("Brief UTF-8 seguro\n", encoding="utf-8")
    pipeline.write_brief_encoding_audit(tmp_path)
    text = (tmp_path / "qa" / "brief_encoding_audit.tsv").read_text(encoding="utf-8")
    assert "mojibake" not in text.lower()
    assert "UTF8_decode_errors\t0\tPASS" in text
