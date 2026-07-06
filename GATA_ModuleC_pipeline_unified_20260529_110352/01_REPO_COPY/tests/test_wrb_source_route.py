import sys
from pathlib import Path


WRB_MASK_FILES = {
    2015: "mask_2015.gpkg",
    2016: "mask_2016.gpkg",
    2017: "mask_2017.gpkg",
    2018: "mask_2018.gpkg",
    2019: "mask_2019.gpkg",
    2020: "mask_2020.gpkg",
    2021: "mask_2021.gpkg",
    2022: "mask_2022_valid_NOHOLES.gpkg",
    2023: "mask_valid_NOHOLES_ardida_2023.gpkg",
    2024: "mask_valid_NOHOLES_ardida_2024.gpkg",
}


def _load_module():
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import wrb_source_route as mod  # type: ignore

    return mod


def _build_wrb_root(tmp_path: Path) -> Path:
    inc_new_root = tmp_path / "Incendios_Nueva version"
    wrb_root = inc_new_root / "WRB"
    overlay_dir = wrb_root / "outputs_qgis_WRB_overlay"
    reference_dir = wrb_root / "Resultados compilados"
    overlay_dir.mkdir(parents=True, exist_ok=True)
    reference_dir.mkdir(parents=True, exist_ok=True)

    for name in ("193.tif", "235.tif", "236.tif", "MostProbable.rat.json"):
        (wrb_root / name).write_text("x", encoding="utf-8")
    (overlay_dir / "MostProbable_assembled.vrt").write_text("<VRTDataset/>", encoding="utf-8")
    (overlay_dir / "WRB_MostProbable_TM06.tif").write_text("legacy", encoding="utf-8")
    (reference_dir / "wrb_burned_2015_2024_long.csv").write_text("Year,Class_name,Area_ha\n", encoding="utf-8")
    for mask_name in WRB_MASK_FILES.values():
        (overlay_dir / mask_name).write_text("mask", encoding="utf-8")
    return inc_new_root


def test_find_wrb_source_bundle_from_inc_new_root(tmp_path):
    mod = _load_module()
    inc_new_root = _build_wrb_root(tmp_path)
    wrb_root = inc_new_root / "WRB"
    overlay_dir = wrb_root / "outputs_qgis_WRB_overlay"
    reference_dir = wrb_root / "Resultados compilados"

    bundle = mod.find_wrb_source_bundle({}, inc_new_root=inc_new_root)

    assert bundle["wrb_root"] == wrb_root
    assert bundle["tile_193"] == wrb_root / "193.tif"
    assert bundle["tile_235"] == wrb_root / "235.tif"
    assert bundle["tile_236"] == wrb_root / "236.tif"
    assert bundle["lookup_path"] == wrb_root / "MostProbable.rat.json"
    assert bundle["assembled_vrt_template"] == overlay_dir / "MostProbable_assembled.vrt"
    assert bundle["reference_csv"] == reference_dir / "wrb_burned_2015_2024_long.csv"


def test_find_wrb_annual_burned_area_paths_prefers_mask_route(tmp_path):
    mod = _load_module()
    inc_new_root = _build_wrb_root(tmp_path)
    overlay_dir = inc_new_root / "WRB" / "outputs_qgis_WRB_overlay"

    annual_paths = mod.find_wrb_annual_burned_area_paths({}, inc_new_root=inc_new_root)

    assert annual_paths == [overlay_dir / WRB_MASK_FILES[year] for year in sorted(WRB_MASK_FILES)]
