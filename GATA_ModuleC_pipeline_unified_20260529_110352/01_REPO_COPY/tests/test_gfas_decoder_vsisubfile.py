from __future__ import annotations

import sys
import types
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import moduleC_pipeline_v2 as mod  # type: ignore

    return mod


class _FakeBand:
    def __init__(self, full_raster):
        self._full_raster = full_raster
        self.read_calls = []

    def GetMetadata(self):
        return {
            "GRIB_COMMENT": "Wildfire flux of Particulate Matter PM2.5 [kg/m2/s]",
            "GRIB_VALID_TIME": "1420156800",
            "GRIB_REF_TIME": "1420156800",
        }

    def GetNoDataValue(self):
        return None

    def ReadAsArray(self, xoff=0, yoff=0, xsize=None, ysize=None):
        self.read_calls.append((xoff, yoff, xsize, ysize))
        if xsize is None or ysize is None:
            return self._full_raster
        return [row[xoff : xoff + xsize] for row in self._full_raster[yoff : yoff + ysize]]


class _FakeDataset:
    def __init__(self, band):
        self._band = band
        self.RasterXSize = len(band._full_raster[0])
        self.RasterYSize = len(band._full_raster)

    def GetRasterBand(self, index):
        assert index == 1
        return self._band

    def GetGeoTransform(self, can_return_null=True):
        return (0.0, 1.0, 0.0, 0.0, 0.0, -1.0)


def test_iter_grib_message_offsets_reports_byte_ranges(tmp_path):
    mod = _load_module()
    src = tmp_path / "sample.grib"
    src.write_bytes(b"GRIBaaaaGRIBbbbbbbGRIBcccc")

    rows = list(mod._iter_grib_message_offsets_by_next_grib(src))

    assert rows == [
        (1, 0, 8),
        (2, 8, 10),
        (3, 18, 8),
    ]


def test_fallback_gfas_pm_rows_from_gribs_uses_year_day_count(tmp_path, monkeypatch):
    mod = _load_module()
    gfas_dir = tmp_path / "CAM-GFAS (ADS)"
    nested = gfas_dir / "_global_official_2015_2024"
    nested.mkdir(parents=True)
    (nested / "GFAS_PM2P5FIRE_2015_GLOBAL_OFFICIAL.grib").write_bytes(b"stub")
    (nested / "GFAS_PM2P5FIRE_2016_GLOBAL_OFFICIAL.grib").write_bytes(b"stub")

    def fail_if_called(_src):
        raise AssertionError("expensive GRIB message counting should not run in filename-year fallback")

    monkeypatch.setattr(mod, "_count_gfas_pm_messages_from_grib", fail_if_called)

    rows = mod._fallback_gfas_pm_rows_from_gribs(gfas_dir)

    assert rows == [
        {
            "file": "_global_official_2015_2024\\GFAS_PM2P5FIRE_2015_GLOBAL_OFFICIAL.grib",
            "minDate": "20150101",
            "message_count": "365",
            "pm_stride_hint": "1",
        },
        {
            "file": "_global_official_2015_2024\\GFAS_PM2P5FIRE_2016_GLOBAL_OFFICIAL.grib",
            "minDate": "20160101",
            "message_count": "366",
            "pm_stride_hint": "1",
        },
    ]


def test_gfas_decoder_reads_message_via_vsisubfile(monkeypatch):
    mod = _load_module()
    full_raster = [
        [0.0, 1.0, 2.0, 3.0, 4.0],
        [10.0, 11.0, 12.0, 13.0, 14.0],
        [20.0, 21.0, 22.0, 23.0, 24.0],
        [30.0, 31.0, 32.0, 33.0, 34.0],
        [40.0, 41.0, 42.0, 43.0, 44.0],
    ]
    band = _FakeBand(full_raster)
    dataset = _FakeDataset(band)
    opened = []

    fake_gdal = types.ModuleType("gdal")
    fake_gdal.Open = lambda path: opened.append(path) or dataset
    fake_gdal.PushErrorHandler = lambda *_args, **_kwargs: None
    fake_gdal.PopErrorHandler = lambda *_args, **_kwargs: None

    fake_osgeo = types.ModuleType("osgeo")
    fake_osgeo.gdal = fake_gdal
    monkeypatch.setitem(sys.modules, "osgeo", fake_osgeo)

    unit_samples = [
        {"unit_id": "A", "unit_name": "Alpha", "unit_level": "NUTS3", "lon": 1.2, "lat": -1.2},
        {"unit_id": "A", "unit_name": "Alpha", "unit_level": "NUTS3", "lon": 2.2, "lat": -2.2},
        {"unit_id": "B", "unit_name": "Beta", "unit_level": "NUTS3", "lon": 3.2, "lat": -3.2},
    ]

    src = Path(r"C:\GFAS\GFAS_PM2P5FIRE_2015_GLOBAL_OFFICIAL.grib")
    result = mod._decode_gfas_pm_subfile_to_unit_rows(
        src,
        src.name,
        1,
        10,
        20,
        "2015-01-01",
        unit_samples,
    )

    assert opened == ["/vsisubfile/10_20,C:/GFAS/GFAS_PM2P5FIRE_2015_GLOBAL_OFFICIAL.grib"]
    assert band.read_calls == [(1, 1, 3, 3)]
    unit_rows = {row["unit_id"]: row for row in result["unit_rows"]}
    assert unit_rows["A"]["pm2p5fire_sum"] == 33.0
    assert unit_rows["B"]["pm2p5fire_sum"] == 33.0
    assert result["inventory_row"][5] == "VSISUBFILE_PM_PAYLOAD"


def test_gfas_decode_chunk_worker_aggregates_rows(monkeypatch):
    mod = _load_module()

    def fake_decode(src_grib, file_name, msg_index, byte_offset, payload_bytes, fallback_date_iso, unit_samples):
        return {
            "inventory_row": [file_name, msg_index, fallback_date_iso, 2015, "", "VSISUBFILE_PM_PAYLOAD", payload_bytes, "", "", "", "PASS"],
            "daily_summary_row": [fallback_date_iso, 2015, file_name, msg_index, 1, 1, 0, 1, 0.0, 1.0, 1.0, 1.0e11, "", "CENTROID_FALLBACK_LIMITED"],
            "daily_row": {
                "date": fallback_date_iso,
                "year": 2015,
                "source_file": file_name,
                "message_index": msg_index,
                "pm2p5fire_mean": float(msg_index),
            },
            "unit_rows": [{"unit_id": f"U{msg_index}", "date": fallback_date_iso}],
        }

    monkeypatch.setattr(mod, "_decode_gfas_pm_subfile_to_unit_rows", fake_decode)

    result = mod._decode_gfas_pm_chunk_worker(
        r"C:\GFAS\GFAS_PM2P5FIRE_2015_GLOBAL_OFFICIAL.grib",
        "GFAS_PM2P5FIRE_2015_GLOBAL_OFFICIAL.grib",
        [
            (1, 10, 20, "2015-01-01"),
            (2, 30, 40, "2015-01-02"),
        ],
        [{"unit_id": "A"}],
    )

    assert result["processed_pm"] == 2
    assert result["last_date"] == "2015-01-02"
    assert [row[1] for row in result["inv_rows"]] == [1, 2]
    assert [row["message_index"] for row in result["daily_rows"]] == [1, 2]
    assert [row["unit_id"] for row in result["unit_rows"]] == ["U1", "U2"]


def test_smoke_route_v0_audit_rows_failed_contract():
    mod = _load_module()
    rows = mod._smoke_route_v0_audit_rows(1, failed=True, detail="decoder exception")
    by_metric = {str(r[0]): r for r in rows}
    assert by_metric["backend_gfas"][2] == "HOLD"
    assert by_metric["backend_era5"][2] == "HOLD"
    assert by_metric["health_exposure_claim"][1] == "BLOCKED_UNLESS_VALIDATED"
    assert by_metric["health_exposure_claim"][2] == "BLOCKED"
    assert by_metric["unexplained_warnings_count"][2] == "BLOCKED"
