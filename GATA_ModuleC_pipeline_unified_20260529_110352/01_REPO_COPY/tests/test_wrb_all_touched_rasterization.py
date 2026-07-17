from pathlib import Path
import sys


class _FakeGeometry:
    def isEmpty(self):
        return False


class _FakeMemoryLayer:
    def featureCount(self):
        return 1


class _FakeBand:
    def Fill(self, _value):
        return None

    def SetNoDataValue(self, _value):
        return None

    def FlushCache(self):
        return None


class _FakeDataset:
    RasterXSize = 4
    RasterYSize = 5

    def __init__(self):
        self.band = _FakeBand()

    def GetGeoTransform(self):
        return (0, 1, 0, 0, 0, -1)

    def SetGeoTransform(self, _gt):
        return None

    def GetProjection(self):
        return 'EPSG:3763'

    def SetProjection(self, _proj):
        return None

    def GetRasterBand(self, _idx):
        return self.band

    def FlushCache(self):
        return None


class _FakeVectorDataset:
    def GetLayer(self, _idx):
        return object()


class _FakeDriver:
    def Create(self, path, *_args, **_kwargs):
        Path(path).touch()
        return _FakeDataset()


class _FakeGdal:
    GDT_Byte = 1
    OF_VECTOR = 1

    def __init__(self):
        self.rasterize_options = None

    def Open(self, _path):
        return _FakeDataset()

    def OpenEx(self, _path, _mode):
        return _FakeVectorDataset()

    def GetDriverByName(self, _name):
        return _FakeDriver()

    def RasterizeLayer(self, _ds, _bands, _layer, burn_values=None, options=None):
        self.rasterize_options = list(options or [])
        return 0


def test_rasterize_annual_burned_area_mask_defaults_to_all_touched_false(tmp_path, monkeypatch):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / 'pipeline' / 'RUN_QGIS' / 'STEP7_MATRIZ_CAUSAL'))
    import step7_matriz_causal as step7  # type: ignore

    fake_gdal = _FakeGdal()
    monkeypatch.setattr(step7, '_load_gdal_runtime', lambda: fake_gdal)
    monkeypatch.setattr(step7, '_save_layer_for_gdal', lambda _layer, path, _processing: path)

    out = tmp_path / 'mask.tif'
    step7._rasterize_annual_burned_area_mask(object(), tmp_path / 'template.tif', out, object())
    assert fake_gdal.rasterize_options == ['ALL_TOUCHED=FALSE']


def test_rasterize_annual_burned_area_mask_can_enable_all_touched_true(tmp_path, monkeypatch):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / 'pipeline' / 'RUN_QGIS' / 'STEP7_MATRIZ_CAUSAL'))
    import step7_matriz_causal as step7  # type: ignore

    fake_gdal = _FakeGdal()
    monkeypatch.setattr(step7, '_load_gdal_runtime', lambda: fake_gdal)
    monkeypatch.setattr(step7, '_save_layer_for_gdal', lambda _layer, path, _processing: path)

    out = tmp_path / 'mask.tif'
    step7._rasterize_annual_burned_area_mask(object(), tmp_path / 'template.tif', out, object(), all_touched=True)
    assert fake_gdal.rasterize_options == ['ALL_TOUCHED=TRUE']


def test_unit_geometry_rescue_uses_all_touched_true(tmp_path, monkeypatch):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / 'pipeline' / 'RUN_QGIS' / 'STEP7_MATRIZ_CAUSAL'))
    import step7_matriz_causal as step7  # type: ignore

    calls = {}
    monkeypatch.setattr(step7, '_build_wrb_geometry_memory_layer', lambda geoms, layer_name='x': _FakeMemoryLayer())

    def fake_rasterize(layer, template_raster, output_mask, processing, all_touched=False):
        calls['all_touched'] = all_touched
        output_mask.touch()
        return output_mask

    monkeypatch.setattr(step7, '_rasterize_annual_burned_area_mask', fake_rasterize)
    monkeypatch.setattr(step7, '_write_masked_wrb_raster', lambda wrb, mask, out: out)
    monkeypatch.setattr(step7, '_count_wrb_classes_in_raster', lambda path: {6: 3.0})

    counts = step7._count_wrb_classes_for_unit_geometries([_FakeGeometry()], tmp_path / 'wrb.tif', tmp_path, 2022, 'U1', object())
    assert calls['all_touched'] is True
    assert counts == {6: 3.0}


def test_wrb_rescue_memory_layer_accepts_multipolygon_geometries():
    repo_root = Path(__file__).resolve().parents[1]
    text = (repo_root / 'pipeline' / 'RUN_QGIS' / 'STEP7_MATRIZ_CAUSAL' / 'step7_matriz_causal.py').read_text(encoding='utf-8')
    assert 'QgsVectorLayer("MultiPolygon?crs=EPSG:3763", layer_name, "memory")' in text
