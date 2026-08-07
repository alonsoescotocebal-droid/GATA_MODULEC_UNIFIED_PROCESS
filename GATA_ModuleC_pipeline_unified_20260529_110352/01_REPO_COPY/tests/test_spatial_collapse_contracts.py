from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
import datetime as dt


def _load_module():
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import moduleC_pipeline_v2 as mod  # type: ignore

    return mod


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _read_tsv_rows(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def test_smoke_route_v0_audit_rows_contract():
    mod = _load_module()
    rows = mod._smoke_route_v0_audit_rows(0, failed=False, detail="")
    by_metric = {str(r[0]): r for r in rows}
    assert by_metric["backend_gfas"][1] == "GDAL"
    assert by_metric["eccodes_for_gfas"][1] == "REJECTED_OR_FORBIDDEN"
    assert by_metric["health_exposure_claim"][1] == "NON_HEALTH_LIMITATION_DECLARED"
    assert by_metric["health_exposure_claim"][2] == "PASS"


def test_finalize_unit_daily_scores_assigns_threshold_and_annual_counts(tmp_path):
    mod = _load_module()
    report = mod.Report(tmp_path / "qa" / "report.txt")
    rows = [
        {
            "unit_id": "PT111",
            "unit_name": "A",
            "unit_level": "NUTS3",
            "date": "2022-01-02",
            "year": 2022,
            "source_file": "f2022.grib",
            "message_index": 1,
            "band_index": 1,
            "pm2p5fire_mean": 1.0e-9,
            "pm2p5fire_max": 1.0e-9,
            "pm2p5fire_sum": 1.0e-9,
            "valid_pixel_count": 1,
            "smoke_day_score": 100.0,
            "spatial_assignment_method": "CENTROID_FALLBACK_LIMITED",
        },
        {
            "unit_id": "PT112",
            "unit_name": "B",
            "unit_level": "NUTS3",
            "date": "2022-01-02",
            "year": 2022,
            "source_file": "f2022.grib",
            "message_index": 1,
            "band_index": 1,
            "pm2p5fire_mean": 2.0e-9,
            "pm2p5fire_max": 2.0e-9,
            "pm2p5fire_sum": 2.0e-9,
            "valid_pixel_count": 1,
            "smoke_day_score": 200.0,
            "spatial_assignment_method": "CENTROID_FALLBACK_LIMITED",
        },
        {
            "unit_id": "PT111",
            "unit_name": "A",
            "unit_level": "NUTS3",
            "date": "2022-01-03",
            "year": 2022,
            "source_file": "f2022.grib",
            "message_index": 3,
            "band_index": 3,
            "pm2p5fire_mean": 3.0e-9,
            "pm2p5fire_max": 3.0e-9,
            "pm2p5fire_sum": 3.0e-9,
            "valid_pixel_count": 1,
            "smoke_day_score": 300.0,
            "spatial_assignment_method": "CENTROID_FALLBACK_LIMITED",
        },
        {
            "unit_id": "PT112",
            "unit_name": "B",
            "unit_level": "NUTS3",
            "date": "2022-01-03",
            "year": 2022,
            "source_file": "f2022.grib",
            "message_index": 3,
            "band_index": 3,
            "pm2p5fire_mean": 4.0e-9,
            "pm2p5fire_max": 4.0e-9,
            "pm2p5fire_sum": 4.0e-9,
            "valid_pixel_count": 1,
            "smoke_day_score": 400.0,
            "spatial_assignment_method": "CENTROID_FALLBACK_LIMITED",
        },
    ]

    finalized, annual, threshold = mod._finalize_unit_daily_scores(rows, report, "test finalize")

    assert threshold is not None
    assert all(r["threshold_id"] == "GFAS_ERA5_PROXY_SMOKE_DAY_P60" for r in finalized)
    assert all("smoke_day_proxy" in r for r in finalized)
    assert all("smoke_day_equivalent" in r for r in finalized)
    assert annual["PT111"][2022]["score_mean"] == 200.0
    assert annual["PT112"][2022]["score_mean"] == 300.0
    assert annual["PT111"][2022]["smoke_days_binary"] == 1.0
    assert annual["PT112"][2022]["smoke_days_binary"] == 1.0
    assert annual["PT111"][2022]["smoke_days"] == 1.0
    assert annual["PT112"][2022]["smoke_days"] == 1.0
    assert round(annual["PT111"][2022]["cumulative_normalized_smoke_intensity_proxy"], 6) == round((100.0 / 300.0) + (300.0 / 300.0), 6)
    assert round(annual["PT112"][2022]["cumulative_normalized_smoke_intensity_proxy"], 6) == round((200.0 / 300.0) + (400.0 / 300.0), 6)
    assert annual["PT111"][2022]["cumulative_normalized_smoke_intensity_proxy"] != annual["PT112"][2022]["cumulative_normalized_smoke_intensity_proxy"]


def test_direct_decoder_helpers_expand_coverage_and_preserve_multi_point_variation():
    mod = _load_module()

    assert mod._planned_pm_message_count(730, 2) == 365
    assert mod._planned_pm_message_count(366, 1) == 366
    assert mod._planned_pm_message_count(93, 1) == 93

    score = mod._direct_unit_smoke_score(2.0, 10.0)
    assert score == ((2.0 * 0.75) + (10.0 * 0.25)) * 1.0e11
    assert score < (10.0 * 1.0e11)
    assert score > (2.0 * 1.0e11)


def test_read_csv_rows_prefers_tab_for_tsv_even_when_detail_contains_semicolons(tmp_path):
    mod = _load_module()
    audit_tsv = tmp_path / "audit.tsv"
    audit_tsv.write_text(
        "metric\tvalue\tstatus\tdetail\n"
        "daily_rows\t94978\tPASS\tdate_unit_pairs=94978; expected_rows_from_dates_x_units=94978\n"
        "unique_years\t10\tPASS\t2015,2016,2017,2018,2019,2020,2021,2022,2023,2024\n",
        encoding="utf-8",
    )

    header, rows, delim = mod.read_csv_rows(audit_tsv)

    assert delim == "\t"
    assert header == ["metric", "value", "status", "detail"]
    assert rows[0]["metric"] == "daily_rows"
    assert rows[0]["detail"].startswith("date_unit_pairs=94978")


def test_spatial_collapse_audit_and_brief_block_claims(tmp_path):
    mod = _load_module()
    output_root = tmp_path / "03_outputs"
    tables = output_root / "tables"
    qa = output_root / "qa"
    brief_dir = output_root / "brief"

    _write(
        tables / "smoke_days_unit_2015_2024.csv",
        "unit_id;year;smoke_days;smoke_method\n"
        "A;2017;100;gfas_proxy\n"
        "B;2017;100;gfas_proxy\n"
        "A;2022;10;gfas_proxy\n"
        "B;2022;10;gfas_proxy\n",
    )
    _write(
        tables / "smoke_day_score_nuts3_daily.csv",
        "unit_id;date;year;smoke_day_score;source_file;method;spatial_assignment\n"
        "A;2017-01-02;2017;100;f2017.grib;gdal;GLOBAL_PORTUGAL_REPLICATED_TO_NUTS3\n"
        "B;2017-01-02;2017;100;f2017.grib;gdal;GLOBAL_PORTUGAL_REPLICATED_TO_NUTS3\n"
        "A;2022-01-02;2022;10;f2022.grib;gdal;GLOBAL_PORTUGAL_REPLICATED_TO_NUTS3\n"
        "B;2022-01-02;2022;10;f2022.grib;gdal;GLOBAL_PORTUGAL_REPLICATED_TO_NUTS3\n",
    )
    _write(
        qa / "gfas_pm2p5fire_portugal_daily_summary.csv",
        "date;year;source_file;rows;numeric;zero;nonzero;min;max;mean;smoke_day_score\n"
        "2017-01-02;2017;f2017.grib;100;100;90;10;0;1;0.1;100\n"
        "2022-01-02;2022;f2022.grib;100;100;99;1;0;1;0.01;10\n",
    )
    _write(
        tables / "IECH_unit_2015_2024.csv",
        "unit_id;year;smoke_days;smoke_hours_equiv;pop;expo_person_hours;IECH\n"
        "A;2017;100;2400;100;240000;2400\n"
        "B;2017;100;2400;200;480000;2400\n"
        "A;2022;10;240;100;24000;240\n"
        "B;2022;10;240;200;48000;240\n",
    )
    _write(
        tables / "IECH_scenarios_2026_2030.csv",
        "unit_id;year;scenario;smoke_days;smoke_hours_equiv;pop;expo_person_hours;IECH;delta_vs_S0\n"
        "A;2026;S0;10;240;100;24000;240;0\n"
        "A;2026;S1;8;192;100;19200;192;-48\n",
    )
    _write(
        qa / "inputs_resolved.json",
        json.dumps(
            {
                "meta": {
                    "smoke_route_selected": "v0_gfas_era5_real",
                    "smoke_route_status": "SCIENTIFIC_PRIMARY_REAL",
                    "smoke_route_decision": "THRESHOLD_DEFINED_AS_INDEXED_METHOD",
                    "health_exposure_claim": "BLOCKED_HEALTH_EXPOSURE_CLAIM",
                }
            }
        ),
    )

    mod.write_spatial_collapse_root_cause_audit(
        output_root=output_root,
        smoke_annual_csv=tables / "smoke_days_unit_2015_2024.csv",
        smoke_daily_csv=tables / "smoke_day_score_nuts3_daily.csv",
        gfas_daily_summary_csv=qa / "gfas_pm2p5fire_portugal_daily_summary.csv",
        iech_hist_csv=tables / "IECH_unit_2015_2024.csv",
    )
    audit_rows = _read_tsv_rows(qa / "spatial_collapse_root_cause_audit.tsv")
    collapse = [r for r in audit_rows if r.get("metric") == "collapse_origin_decision"]
    assert collapse and collapse[0]["value"] == "COLLAPSE_ORIGIN_MULTIPLE"

    report = mod.Report(qa / "report_auditoria_v2.txt")
    brief_path = mod.brief_generate(tables, brief_dir, report)
    text = brief_path.read_text(encoding="utf-8").lower()

    assert len(text) > 1200
    assert "line 001: iech pipeline v2 audit detail line." not in text
    assert "highest iech" not in text
    assert "elevated iech" not in text
    assert "smoke hotspot" not in text
    assert "spatially differentiated smoke exposure" not in text
    assert "most exposed by smoke" not in text
    assert "spatial ranking from smoke proxy is blocked" in text
    assert "population smoke-day burden is unavailable or invalid" in text


def test_probe_gfas_pm_message_pattern_prefers_min_date_hint_when_valid_time_is_one_day_late(tmp_path, monkeypatch):
    mod = _load_module()
    src = tmp_path / "GFAS_PM2P5FIRE_2015_GLOBAL_OFFICIAL.grib"
    src.write_bytes(b"probe")
    late_valid_time = str(int(dt.datetime(2015, 1, 2, tzinfo=dt.timezone.utc).timestamp()))

    monkeypatch.setattr(mod, "_iter_grib_messages_by_next_grib", lambda _src: iter([(1, b"pm", 0)]))
    monkeypatch.setattr(
        mod,
        "_read_grib_message_metadata_from_payload",
        lambda _payload, _token: {"GRIB_COMMENT": "PM2P5FIRE", "GRIB_VALID_TIME": late_valid_time},
    )
    monkeypatch.setattr(mod, "_grib_comment_is_pm2p5fire", lambda _comment: True)

    pm_start_index, base_date = mod._probe_gfas_pm_message_pattern(src, "2015-01-01")

    assert pm_start_index == 1
    assert base_date == "2015-01-01"


def test_probe_gfas_pm_message_pattern_uses_metadata_date_without_hint(tmp_path, monkeypatch):
    mod = _load_module()
    src = tmp_path / "GFAS_PM2P5FIRE_2015_GLOBAL_OFFICIAL.grib"
    src.write_bytes(b"probe")
    valid_time = str(int(dt.datetime(2015, 1, 2, tzinfo=dt.timezone.utc).timestamp()))

    monkeypatch.setattr(mod, "_iter_grib_messages_by_next_grib", lambda _src: iter([(1, b"pm", 0)]))
    monkeypatch.setattr(
        mod,
        "_read_grib_message_metadata_from_payload",
        lambda _payload, _token: {"GRIB_COMMENT": "PM2P5FIRE", "GRIB_VALID_TIME": valid_time},
    )
    monkeypatch.setattr(mod, "_grib_comment_is_pm2p5fire", lambda _comment: True)

    pm_start_index, base_date = mod._probe_gfas_pm_message_pattern(src, "")

    assert pm_start_index == 1
    assert base_date == "2015-01-02"


def test_resolve_gfas_pm_date_prefers_fallback_when_metadata_is_one_day_late():
    mod = _load_module()

    assert mod._resolve_gfas_pm_date("2015-01-02", "2015-01-01") == "2015-01-01"


def test_resolve_gfas_pm_date_preserves_actual_date_when_not_shifted():
    mod = _load_module()

    assert mod._resolve_gfas_pm_date("2015-01-01", "2015-01-01") == "2015-01-01"
    assert mod._resolve_gfas_pm_date("2015-01-03", "2015-01-01") == "2015-01-03"
    assert mod._resolve_gfas_pm_date("", "2015-01-01") == "2015-01-01"
