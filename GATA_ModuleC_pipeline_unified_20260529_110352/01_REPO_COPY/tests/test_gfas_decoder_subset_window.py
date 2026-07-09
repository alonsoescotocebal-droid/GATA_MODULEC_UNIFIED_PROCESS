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
        return {}

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


def test_gfas_decoder_reads_only_sample_bbox(monkeypatch):
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

    fake_gdal = types.ModuleType("gdal")
    fake_gdal.FileFromMemBuffer = lambda *_args, **_kwargs: None
    fake_gdal.Open = lambda *_args, **_kwargs: dataset
    fake_gdal.Unlink = lambda *_args, **_kwargs: None
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

    result = mod._decode_gfas_pm_payload_to_unit_rows(
        b"payload",
        "GFAS_PM2P5FIRE_2015_GLOBAL_OFFICIAL.grib",
        1,
        "2015-01-01",
        unit_samples,
    )

    assert band.read_calls == [(1, 1, 3, 3)]

    unit_rows = {row["unit_id"]: row for row in result["unit_rows"]}
    assert unit_rows["A"]["pm2p5fire_sum"] == 33.0
    assert unit_rows["A"]["pm2p5fire_mean"] == 16.5
    assert unit_rows["A"]["pm2p5fire_max"] == 22.0
    assert unit_rows["A"]["valid_pixel_count"] == 2
    assert unit_rows["A"]["smoke_day_score"] == mod._direct_unit_smoke_score(16.5, 22.0)
    assert unit_rows["B"]["pm2p5fire_sum"] == 33.0
    assert unit_rows["B"]["pm2p5fire_mean"] == 33.0
    assert unit_rows["B"]["pm2p5fire_max"] == 33.0
    assert unit_rows["B"]["valid_pixel_count"] == 1
    assert result["daily_row"]["date"] == "2015-01-01"
